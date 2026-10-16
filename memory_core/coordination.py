"""Coordination primitives: task management, atomic claiming, and optimistic shared state (CAS)."""

from __future__ import annotations

import re
import uuid
from typing import Any

from memory_core.clock import now as get_now
from memory_core.clock import now_ms as get_now_ms
from memory_core.db import TenantDB, get_tenant_db
from memory_core.errors import ConflictError, InvalidInputError, NotFoundError
from memory_core.queries import (
    Q_STATE_CAS,
    Q_STATE_GET,
    Q_TASK_CLAIM,
    Q_TASK_CLAIM_NEXT,
    Q_TASK_CREATE,
    Q_TASK_DONE,
    Q_TASK_LINK_USER,
)

KEY_REGEX: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


# ---------------------------------------------------------------------------
# 1. Task Operations
# ---------------------------------------------------------------------------


async def create_task(
    tenant_id: str,
    title: str,
    priority: int = 1,
    user_id: str | None = None,
    task_id: str | None = None,
) -> str:
    """Create a new coordination task in OPEN status."""
    db: TenantDB = await get_tenant_db(tenant_id)
    tid: str = task_id or f"task-{uuid.uuid4().hex[:8]}"
    ts_ms: int = get_now_ms()

    await db.run_rw(
        Q_TASK_CREATE,
        {
            "id": tid,
            "title": title,
            "prio": int(priority),
            "ts": ts_ms,
        },
    )

    if user_id:
        await db.run_rw(
            Q_TASK_LINK_USER,
            {"id": tid, "uid": user_id},
        )

    return tid


async def claim_task(
    tenant_id: str,
    task_id: str,
    agent_id: str,
) -> int:
    """Atomically claim an OPEN task for an agent, incrementing version."""
    db: TenantDB = await get_tenant_db(tenant_id)
    res: list[Any] = await db.run_rw(
        Q_TASK_CLAIM,
        {"id": task_id, "agent": agent_id},
    )
    if res:
        return int(res[0][1])

    # Inspect failure reason
    check_res: list[Any] = await db.run_ro(
        "MATCH (t:Task {id: $id}) RETURN t.status, t.version",
        {"id": task_id},
    )
    if not check_res:
        raise NotFoundError(f"Task '{task_id}' not found in tenant '{tenant_id}'")

    current_status: str = str(check_res[0][0])
    current_version: int = int(check_res[0][1])
    raise ConflictError(
        f"Task '{task_id}' cannot be claimed: status is '{current_status}' (expected 'OPEN')",
        current_version=current_version,
    )


async def claim_next(
    tenant_id: str,
    agent_id: str,
) -> dict[str, Any]:
    """Atomically pick and claim the highest priority OPEN task."""
    db: TenantDB = await get_tenant_db(tenant_id)
    res: list[Any] = await db.run_rw(
        Q_TASK_CLAIM_NEXT,
        {"agent": agent_id},
    )
    if not res:
        raise NotFoundError("No open tasks available to claim")

    return {
        "id": str(res[0][0]),
        "title": str(res[0][1]),
        "version": int(res[0][2]),
    }


async def complete_task(
    tenant_id: str,
    task_id: str,
    agent_id: str,
) -> None:
    """Mark a CLAIMED task as DONE by the claiming agent."""
    db: TenantDB = await get_tenant_db(tenant_id)
    res: list[Any] = await db.run_rw(
        Q_TASK_DONE,
        {"id": task_id, "agent": agent_id},
    )
    if not res:
        check_res: list[Any] = await db.run_ro(
            "MATCH (t:Task {id: $id}) RETURN t.status, t.claimed_by",
            {"id": task_id},
        )
        if not check_res:
            raise NotFoundError(f"Task '{task_id}' not found in tenant '{tenant_id}'")
        raise ConflictError(
            f"Cannot complete task '{task_id}': status='{check_res[0][0]}', claimed_by='{check_res[0][1]}'"
        )


# ---------------------------------------------------------------------------
# 2. Shared State (Optimistic Concurrency Control / CAS)
# ---------------------------------------------------------------------------


def _validate_state_key(key: str) -> None:
    """Ensure state key matches lowercase snake_case identifier constraint."""
    if not KEY_REGEX.match(key):
        raise InvalidInputError(
            f"Invalid state key '{key}'. Must match pattern '^[a-z][a-z0-9_]{{0,31}}$'"
        )


async def get_state(
    tenant_id: str,
    session_id: str,
    key: str,
) -> dict[str, Any]:
    """Retrieve the value and version of a session state entry."""
    _validate_state_key(key)
    db: TenantDB = await get_tenant_db(tenant_id)
    res: list[Any] = await db.run_ro(
        Q_STATE_GET,
        {"sid": session_id, "key": key},
    )
    if not res:
        raise NotFoundError(f"State key '{key}' not found for session '{session_id}'")

    return {
        "value": str(res[0][0]),
        "version": int(res[0][1]),
    }


async def set_state(
    tenant_id: str,
    session_id: str,
    key: str,
    value: str,
    expected_version: int,
    agent_id: str,
) -> int:
    """Atomically create or update a shared session state entry with version checking."""
    _validate_state_key(key)
    if len(value) > 2000:
        raise InvalidInputError("State value exceeds maximum length of 2000 characters")

    db: TenantDB = await get_tenant_db(tenant_id)
    eid: str = f"st-{session_id}-{key}"
    ts: int = get_now()

    if expected_version == 0:
        # Atomic creation via MERGE with ON CREATE per Section 6.5 fallback
        create_cypher: str = (
            "MATCH (s:Session {id: $sid}) "
            "MERGE (e:StateEntry {id: $eid}) "
            "ON CREATE SET e.key = $key, e.value = $value, e.version = 1, "
            "              e.updated_by = $agent, e.updated_at = $ts "
            "MERGE (s)-[:HAS_STATE]->(e) "
            "RETURN e.version AS version, e.value AS value"
        )
        res: list[Any] = await db.run_rw(
            create_cypher,
            {
                "sid": session_id,
                "eid": eid,
                "key": key,
                "value": value,
                "agent": agent_id,
                "ts": ts,
            },
        )
        if not res:
            raise NotFoundError(f"Session '{session_id}' not found in tenant '{tenant_id}'")

        actual_version: int = int(res[0][0])
        actual_value: str = str(res[0][1])
        if actual_version != 1 or actual_value != value:
            raise ConflictError(
                f"State entry '{key}' already exists with version {actual_version}",
                current_version=actual_version,
            )
        return 1

    # Update existing state with CAS
    res = await db.run_rw(
        Q_STATE_CAS,
        {
            "eid": eid,
            "expected": expected_version,
            "value": value,
            "agent": agent_id,
            "ts": ts,
        },
    )
    if res:
        return int(res[0][0])

    # Inspect current state to report conflict
    current_res: list[Any] = await db.run_ro(
        "MATCH (e:StateEntry {id: $eid}) RETURN e.version",
        {"eid": eid},
    )
    if not current_res:
        raise NotFoundError(f"State key '{key}' not found for session '{session_id}'")

    current_ver: int = int(current_res[0][0])
    raise ConflictError(
        f"CAS mismatch for key '{key}': expected {expected_version}, found {current_ver}",
        current_version=current_ver,
    )


# ---------------------------------------------------------------------------
# 3. Routing
# ---------------------------------------------------------------------------


async def route(
    tenant_id: str,
    topic_id: str,
) -> list[str]:
    """Find available expert agents for a topic ordered by current task load."""
    db: TenantDB = await get_tenant_db(tenant_id)

    # Validate that entity exists and has type='topic'
    check_topic: list[Any] = await db.run_ro(
        "MATCH (e:Entity {id: $topic}) RETURN e.type",
        {"topic": topic_id},
    )
    if not check_topic or str(check_topic[0][0]) != "topic":
        raise NotFoundError(f"Topic entity '{topic_id}' not found or not a topic")

    res: list[Any] = await db.run_ro(
        "MATCH (a:Agent {status: 'AVAILABLE'})-[:EXPERT_IN]->(e:Entity {id: $topic}) "
        "OPTIONAL MATCH (t:Task) WHERE t.status = 'CLAIMED' AND t.claimed_by = a.id "
        "RETURN a.id AS id, a.name AS name, count(t) AS load "
        "ORDER BY load ASC, id ASC",
        {"topic": topic_id},
    )
    return [str(row[0]) for row in res]


# ---------------------------------------------------------------------------
# 4. Handoff Protocol
# ---------------------------------------------------------------------------


async def create_handoff(
    tenant_id: str,
    session_id: str,
    from_agent: str,
    to_agent: str,
    reason: str,
    now_ts: int | None = None,
) -> dict[str, Any]:
    """Create a handoff bundle transferring context to another specialist agent."""
    if from_agent == to_agent:
        raise InvalidInputError(f"Cannot hand off to the same agent ('{from_agent}')")

    db: TenantDB = await get_tenant_db(tenant_id)
    current_time: int = now_ts if now_ts is not None else get_now()

    # Validate session exists, is OPEN, and get user
    sess_res: list[Any] = await db.run_ro(
        "MATCH (s:Session {id: $sid}) RETURN s.status, s.user_id",
        {"sid": session_id},
    )
    if not sess_res:
        raise NotFoundError(f"Session '{session_id}' not found in tenant '{tenant_id}'")

    sess_status: str = str(sess_res[0][0])
    user_id: str = str(sess_res[0][1])
    if sess_status != "OPEN":
        raise ConflictError(f"Cannot create handoff for session '{session_id}' in status '{sess_status}'")

    # Validate both agents exist
    agents_res: list[Any] = await db.run_ro(
        "MATCH (a:Agent) WHERE a.id IN [$a1, $a2] RETURN a.id",
        {"a1": from_agent, "a2": to_agent},
    )
    found_agents: set[str] = {str(r[0]) for r in agents_res}
    if from_agent not in found_agents:
        raise NotFoundError(f"Source agent '{from_agent}' not found")
    if to_agent not in found_agents:
        raise NotFoundError(f"Target agent '{to_agent}' not found")

    # Determine query text from last user message (fallback: reason)
    user_msg_res: list[Any] = await db.run_ro(
        "MATCH (s:Session {id: $sid})-[:HAS_MESSAGE]->(m:Message {role: 'user'}) "
        "RETURN m.text ORDER BY m.seq DESC LIMIT 1",
        {"sid": session_id},
    )
    query_text: str = str(user_msg_res[0][0]) if user_msg_res else reason

    # Retrieve context bundle via recall
    from memory_core.recall import recall
    recall_res: dict[str, Any] = await recall(
        tenant_id=tenant_id,
        user_id=user_id,
        query=query_text,
        k=2,
        now_ts=current_time,
    )

    fact_ids: list[str] = [f["id"] for f in recall_res.get("facts", [])]
    ep_ids: list[str] = [ep["id"] for ep in recall_res.get("episodes", [])[:2]]
    proc_ids: list[str] = [p["id"] for p in recall_res.get("procedures", [])[:1]]

    # Last 6 messages of session
    msg_res: list[Any] = await db.run_ro(
        "MATCH (s:Session {id: $sid})-[:HAS_MESSAGE]->(m:Message) "
        "RETURN m.id ORDER BY m.seq DESC LIMIT 6",
        {"sid": session_id},
    )
    msg_ids: list[str] = [str(r[0]) for r in reversed(msg_res)]

    # Create Handoff node
    hid: str = f"hof-{uuid.uuid4().hex[:8]}"
    await db.run_rw(
        "MATCH (a:Agent {id: $from}), (b:Agent {id: $to}), (s:Session {id: $sid}) "
        "CREATE (h:Handoff {id: $hid, status: 'PENDING', reason: $reason, from_agent: $from, "
        "                   to_agent: $to, session_id: $sid, version: 1, created_at: $ts}) "
        "CREATE (a)-[:HANDED_OFF]->(h) "
        "CREATE (h)-[:TO]->(b) "
        "CREATE (h)-[:FOR_SESSION]->(s) "
        "RETURN h.id AS id",
        {
            "from": from_agent,
            "to": to_agent,
            "sid": session_id,
            "hid": hid,
            "reason": reason,
            "ts": current_time,
        },
    )

    # Attach carried bundle elements
    kind_mappings: list[tuple[str, str, list[str]]] = [
        ("Fact", "fact", fact_ids),
        ("Episode", "episode", ep_ids),
        ("Procedure", "procedure", proc_ids),
        ("Message", "message", msg_ids),
    ]

    for label, kind, ids in kind_mappings:
        if ids:
            cypher = (
                f"MATCH (h:Handoff {{id: $hid}}) "
                f"UNWIND $ids AS xid "
                f"MATCH (x:{label} {{id: xid}}) "
                f"CREATE (h)-[:CARRIES {{kind: $kind}}]->(x)"
            )
            await db.run_rw(cypher, {"hid": hid, "ids": ids, "kind": kind})

    carries_dict: dict[str, int] = {
        "fact": len(fact_ids),
        "episode": len(ep_ids),
        "procedure": len(proc_ids),
        "message": len(msg_ids),
    }
    carries_total: int = sum(carries_dict.values())

    return {
        "handoff_id": hid,
        "carries": carries_dict,
        "carries_total": carries_total,
    }


async def accept_handoff(
    tenant_id: str,
    handoff_id: str,
    agent_id: str,
    now_ts: int | None = None,
) -> dict[str, Any]:
    """Atomically accept a pending handoff, switching the session's active agent."""
    db: TenantDB = await get_tenant_db(tenant_id)
    current_time: int = now_ts if now_ts is not None else get_now()

    res: list[Any] = await db.run_rw(
        "MATCH (h:Handoff {id: $hid, status: 'PENDING', to_agent: $agent}) "
        "SET h.status = 'ACCEPTED', h.accepted_at = $ts, h.version = h.version + 1 "
        "RETURN h.id AS id",
        {"hid": handoff_id, "agent": agent_id, "ts": current_time},
    )

    if not res:
        # Inspect failure state
        read_res: list[Any] = await db.run_ro(
            "MATCH (h:Handoff {id: $hid}) RETURN h.status AS status, h.to_agent AS to_agent, h.session_id AS sid",
            {"hid": handoff_id},
        )
        if not read_res:
            raise NotFoundError(f"Handoff '{handoff_id}' not found in tenant '{tenant_id}'")

        status: str = str(read_res[0][0])
        target_agent: str = str(read_res[0][1])

        from memory_core.errors import ForbiddenError
        if target_agent != agent_id:
            raise ForbiddenError(
                f"Agent '{agent_id}' is not authorized to accept handoff intended for '{target_agent}'"
            )
        if status != "PENDING":
            raise ConflictError(f"Handoff '{handoff_id}' is in status '{status}' (expected 'PENDING')")

    # Update session active agent
    session_res: list[Any] = await db.run_ro(
        "MATCH (h:Handoff {id: $hid}) RETURN h.session_id",
        {"hid": handoff_id},
    )
    sid: str = str(session_res[0][0])
    await db.run_rw(
        "MATCH (s:Session {id: $sid}) SET s.current_agent = $agent RETURN s.id AS id",
        {"sid": sid, "agent": agent_id},
    )

    # Fetch bundle details
    bundle_rows: list[Any] = await db.run_ro(
        "MATCH (h:Handoff {id: $hid})-[c:CARRIES]->(x) "
        "RETURN c.kind AS kind, x.id AS id, x.summary AS summary, x.predicate AS predicate, "
        "       x.object AS object, x.name AS name, x.text AS text, x.role AS role",
        {"hid": handoff_id},
    )

    bundle: list[dict[str, Any]] = [
        {
            "kind": row[0],
            "id": row[1],
            "summary": row[2],
            "predicate": row[3],
            "object": row[4],
            "name": row[5],
            "text": row[6],
            "role": row[7],
        }
        for row in bundle_rows
    ]

    return {
        "handoff_id": handoff_id,
        "session_id": sid,
        "bundle": bundle,
    }


async def complete_handoff(
    tenant_id: str,
    handoff_id: str,
    agent_id: str,
    outcome: str,
    summary: str,
    now_ts: int | None = None,
) -> None:
    """Complete an accepted handoff, recording outcome and summary."""
    db: TenantDB = await get_tenant_db(tenant_id)
    current_time: int = now_ts if now_ts is not None else get_now()

    res: list[Any] = await db.run_rw(
        "MATCH (h:Handoff {id: $hid, status: 'ACCEPTED', to_agent: $agent}) "
        "SET h.status = 'COMPLETED', h.completed_at = $ts, h.outcome = $outcome, "
        "    h.summary = $summary, h.version = h.version + 1 "
        "RETURN h.id AS id",
        {
            "hid": handoff_id,
            "agent": agent_id,
            "ts": current_time,
            "outcome": outcome,
            "summary": summary,
        },
    )

    if not res:
        read_res: list[Any] = await db.run_ro(
            "MATCH (h:Handoff {id: $hid}) RETURN h.status AS status, h.to_agent AS to_agent",
            {"hid": handoff_id},
        )
        if not read_res:
            raise NotFoundError(f"Handoff '{handoff_id}' not found in tenant '{tenant_id}'")

        status: str = str(read_res[0][0])
        target_agent: str = str(read_res[0][1])

        from memory_core.errors import ForbiddenError
        if target_agent != agent_id:
            raise ForbiddenError(
                f"Agent '{agent_id}' is not authorized to complete handoff intended for '{target_agent}'"
            )
        if status != "ACCEPTED":
            raise ConflictError(f"Handoff '{handoff_id}' is in status '{status}' (expected 'ACCEPTED')")


async def pending_handoffs(
    tenant_id: str,
    agent_id: str,
) -> list[dict[str, Any]]:
    """List all pending handoffs targeted to a specific agent in chronological order."""
    db: TenantDB = await get_tenant_db(tenant_id)
    rows: list[Any] = await db.run_ro(
        "MATCH (h:Handoff {status: 'PENDING', to_agent: $agent}) "
        "RETURN h.id AS id, h.reason AS reason, h.from_agent AS from_agent, "
        "       h.session_id AS session_id, h.created_at AS created_at "
        "ORDER BY h.created_at",
        {"agent": agent_id},
    )
    return [
        {
            "id": str(r[0]),
            "reason": str(r[1]),
            "from_agent": str(r[2]),
            "session_id": str(r[3]),
            "created_at": int(r[4]),
        }
        for r in rows
    ]

