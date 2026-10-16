"""Unit and golden tests for session consolidation, episodic creation, and fact extraction (G9)."""

from __future__ import annotations

from typing import Any

import pytest

from memory_core.consolidation import close_session
from memory_core.db import TenantDB, get_tenant_db
from memory_core.errors import ConflictError
from memory_core.history import append_message, create_session
from seed.seed import seed_tenant


@pytest.mark.asyncio
async def test_g9_consolidation() -> None:
    """Verify G9: close_session creates episode with exact importance, associations, and CLOSED status."""
    await seed_tenant("acme", reset=True)
    db: TenantDB = await get_tenant_db("acme")

    session_id = "sess-demo-continuity"

    # Create session for Priya
    await create_session(
        tenant_id="acme",
        user_id="user-priya",
        current_agent="agent-triage",
        session_id=session_id,
    )

    # Append user inquiry and agent responses
    await append_message(
        tenant_id="acme",
        session_id=session_id,
        role="user",
        text="I noticed a duplicate charge on invoice INV-1042. Can you refund it?",
    )
    await append_message(
        tenant_id="acme",
        session_id=session_id,
        role="agent",
        agent_id="agent-triage",
        text="Connecting you to Billing to process the duplicate refund.",
    )
    await append_message(
        tenant_id="acme",
        session_id=session_id,
        role="agent",
        agent_id="agent-billing",
        text="I have reviewed invoice INV-1042 and issued your refund.",
    )

    # Create Handoff node to satisfy G9 handoff condition
    await db.run_rw(
        "CREATE (h:Handoff {id: 'hof-demo-1', session_id: $sid, status: 'COMPLETED'})",
        {"sid": session_id},
    )

    # Execute consolidation
    res: dict[str, Any] = await close_session(
        tenant_id="acme",
        session_id=session_id,
        outcome="resolved",
    )

    # 1. Assert return values
    assert res["episode_id"] == f"ep-{session_id}"
    assert res["importance"] == 0.8  # 0.6 base + 0.2 handoff

    # 2. Verify Episode properties in graph
    ep_rows: list[Any] = await db.run_ro(
        "MATCH (e:Episode {id: $eid}) "
        "RETURN e.id, e.importance, e.status, e.outcome",
        {"eid": f"ep-{session_id}"},
    )
    assert len(ep_rows) == 1
    assert ep_rows[0][0] == f"ep-{session_id}"
    assert float(ep_rows[0][1]) == 0.8
    assert ep_rows[0][2] == "ACTIVE"
    assert ep_rows[0][3] == "resolved"

    # 3. Verify ABOUT user-priya
    about_rows: list[Any] = await db.run_ro(
        "MATCH (e:Episode {id: $eid})-[:ABOUT]->(u:User) RETURN u.id",
        {"eid": f"ep-{session_id}"},
    )
    assert len(about_rows) == 1
    assert about_rows[0][0] == "user-priya"

    # 4. Verify INVOLVED agents = {agent-triage, agent-billing}
    inv_rows: list[Any] = await db.run_ro(
        "MATCH (e:Episode {id: $eid})-[:INVOLVED]->(a:Agent) RETURN a.id",
        {"eid": f"ep-{session_id}"},
    )
    inv_agents = {r[0] for r in inv_rows}
    assert inv_agents == {"agent-triage", "agent-billing"}

    # 5. Verify MENTIONS contains {topic-billing, topic-refunds, invoice-inv-1042}
    ment_rows: list[Any] = await db.run_ro(
        "MATCH (e:Episode {id: $eid})-[:MENTIONS]->(x:Entity) RETURN x.id",
        {"eid": f"ep-{session_id}"},
    )
    mentions = {r[0] for r in ment_rows}
    assert {"topic-billing", "topic-refunds", "invoice-inv-1042"}.issubset(mentions), (
        f"Missing required entity mentions: {mentions}"
    )

    # 6. Verify (sess)-[:SUMMARIZED_AS]->(episode)
    sum_rows: list[Any] = await db.run_ro(
        "MATCH (s:Session {id: $sid})-[:SUMMARIZED_AS]->(e:Episode {id: $eid}) RETURN count(e)",
        {"sid": session_id, "eid": f"ep-{session_id}"},
    )
    assert sum_rows[0][0] == 1

    # 7. Verify session status is CLOSED
    sess_status_res: list[Any] = await db.run_ro(
        "MATCH (s:Session {id: $sid}) RETURN s.status, s.outcome",
        {"sid": session_id},
    )
    assert sess_status_res[0][0] == "CLOSED"
    assert sess_status_res[0][1] == "resolved"

    # 8. Closing an already closed session raises ConflictError
    with pytest.raises(ConflictError):
        await close_session(
            tenant_id="acme",
            session_id=session_id,
            outcome="resolved",
        )
