"""Consolidation layer creating structured episodes, extracting facts, and closing sessions."""

from __future__ import annotations

import re
from typing import Any

from memory_core.clock import now as get_now
from memory_core.db import TenantDB, get_tenant_db
from memory_core.embedder import get_embedder, stem, tokens
from memory_core.errors import ConflictError, InvalidInputError, NotFoundError
from memory_core.procedural import promote_procedures
from memory_core.queries import (
    Q_EP_CREATE,
    Q_EP_LINK_AGENTS,
    Q_EP_LINK_ENTITIES,
)
from memory_core.semantic import remember_fact

VALID_OUTCOMES: set[str] = {"resolved", "escalated", "abandoned"}


async def close_session(
    tenant_id: str,
    session_id: str,
    outcome: str,
    summary: str | None = None,
) -> dict[str, Any]:
    """Close an active session, synthesize an episodic memory, extract facts, and promote procedures."""
    if outcome not in VALID_OUTCOMES:
        raise InvalidInputError(
            f"Invalid outcome '{outcome}'. Must be one of {sorted(VALID_OUTCOMES)}"
        )

    db: TenantDB = await get_tenant_db(tenant_id)
    embedder = get_embedder()
    current_time: int = get_now()

    # 1. Load session and verify it is not already CLOSED
    sess_res: list[Any] = await db.run_ro(
        "MATCH (s:Session {id: $sid}) RETURN s.id, s.status, s.user_id",
        {"sid": session_id},
    )
    if not sess_res:
        raise NotFoundError(f"Session '{session_id}' not found in tenant '{tenant_id}'")

    sess_status: str = str(sess_res[0][1])
    user_id: str = str(sess_res[0][2])
    if sess_status == "CLOSED":
        raise ConflictError(f"Session '{session_id}' is already CLOSED")

    # Fetch user name
    user_res: list[Any] = await db.run_ro(
        "MATCH (u:User {id: $uid}) RETURN u.name",
        {"uid": user_id},
    )
    user_name: str = str(user_res[0][0]) if user_res else "User"

    # 2. Load all messages for the session
    msg_rows: list[Any] = await db.run_ro(
        "MATCH (s:Session {id: $sid})-[:HAS_MESSAGE]->(m:Message) "
        "RETURN m.seq AS seq, m.role AS role, m.agent_id AS agent_id, m.text AS text "
        "ORDER BY m.seq ASC",
        {"sid": session_id},
    )

    first_user_text: str = ""
    agents_involved: set[str] = set()
    message_texts: list[str] = []
    user_messages: list[str] = []

    for row in msg_rows:
        role: str = str(row[1])
        agent_id: str = str(row[2]) if row[2] else ""
        text: str = str(row[3])
        message_texts.append(text)

        if role == "user":
            user_messages.append(text)
            if not first_user_text:
                first_user_text = text
        elif role == "agent" and agent_id:
            agents_involved.add(agent_id)

    # 3. Determine episode summary
    if summary and summary.strip():
        ep_summary: str = summary.strip()
    else:
        ep_summary = f"{user_name}: {first_user_text}. Outcome: {outcome}."

    # 4. Entity extraction: match stemmed message tokens against Entity keywords
    entity_rows: list[Any] = await db.run_ro(
        "MATCH (x:Entity) RETURN x.id AS id, x.keywords AS keywords"
    )
    all_message_stems: set[str] = set()
    for text in message_texts:
        for t in tokens(text):
            all_message_stems.add(stem(t))

    matched_entity_ids: list[str] = []
    for erow in entity_rows:
        eid: str = str(erow[0])
        kw_list: list[str] = list(erow[1]) if erow[1] else []
        if any(kw in all_message_stems for kw in kw_list):
            matched_entity_ids.append(eid)

    # 5. Calculate importance score
    base_importance: float = 0.6 if outcome == "resolved" else (0.4 if outcome == "escalated" else 0.2)

    # Check if handoff occurred
    handoff_check: list[Any] = await db.run_ro(
        "MATCH (h:Handoff {session_id: $sid}) RETURN count(h)",
        {"sid": session_id},
    )
    if handoff_check and int(handoff_check[0][0]) > 0:
        base_importance += 0.2

    # Check if any fact was created or superseded in this session
    fact_check: list[Any] = await db.run_ro(
        "MATCH (f:Fact)-[:DERIVED_FROM]->(s:Session {id: $sid}) RETURN count(f)",
        {"sid": session_id},
    )
    if fact_check and int(fact_check[0][0]) > 0:
        base_importance += 0.1

    final_importance: float = min(1.0, round(base_importance, 2))

    # 6. Create Episode node
    episode_id: str = f"ep-{session_id}"
    emb: list[float] = embedder.embed(ep_summary)

    await db.run_rw(
        Q_EP_CREATE,
        {
            "uid": user_id,
            "sid": session_id,
            "eid": episode_id,
            "summary": ep_summary,
            "outcome": outcome,
            "imp": final_importance,
            "ts": current_time,
            "emb": emb,
        },
    )

    if matched_entity_ids:
        await db.run_rw(
            Q_EP_LINK_ENTITIES,
            {"eid": episode_id, "ids": matched_entity_ids},
        )

    if agents_involved:
        await db.run_rw(
            Q_EP_LINK_AGENTS,
            {"eid": episode_id, "ids": sorted(agents_involved)},
        )

    # 7. Rule-based fact extraction over user messages
    facts_changed: list[str] = []
    rule_patterns: list[tuple[str, str]] = [
        (r"i prefer (email|phone|chat)", "prefers_channel"),
        (r"moved to ([a-z]+)", "city"),
        (r"plan is ([a-z]+)", "plan"),
    ]

    for utext in user_messages:
        text_lower: str = utext.lower()
        for pattern, pred in rule_patterns:
            match = re.search(pattern, text_lower)
            if match:
                obj_val: str = match.group(1)
                # Skip if active fact with same pred & obj already derived from this session
                existing_fact: list[Any] = await db.run_ro(
                    "MATCH (f:Fact {predicate: $pred, object: $obj, status: 'ACTIVE'})"
                    "-[:DERIVED_FROM]->(s:Session {id: $sid}) RETURN f.id",
                    {"pred": pred, "obj": obj_val, "sid": session_id},
                )
                if not existing_fact:
                    res_f = await remember_fact(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        predicate=pred,
                        object_=obj_val,
                        session_id=session_id,
                    )
                    facts_changed.append(str(res_f["fact_id"]))

    # 8. Promote candidate procedures that have met threshold criteria
    promoted: list[str] = await promote_procedures(tenant_id)

    # 9. Mark session as CLOSED
    await db.run_rw(
        "MATCH (s:Session {id: $sid}) SET s.status = 'CLOSED', s.ended_at = $ts, s.outcome = $outcome",
        {"sid": session_id, "ts": current_time, "outcome": outcome},
    )

    return {
        "episode_id": episode_id,
        "importance": final_importance,
        "facts_changed": facts_changed,
        "promoted": promoted,
    }
