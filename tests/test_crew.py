"""Tests for the multi-agent crew runner and handoff chaining."""

from __future__ import annotations

import pytest

from backend.crew import run_turn
from backend.events import EventBus
from backend.mcp_bridge import MemoryContext
from memory_core.clock import now
from memory_core.db import get_tenant_db


@pytest.mark.asyncio
async def test_crew_continuity_handoff_chaining():
    """Verify that crew.run_turn chains from triage to specialist and closes with final."""
    db = await get_tenant_db("acme")
    sid = "sess-test-crew-chain"
    uid = "user-priya"

    # Reset test session state
    await db.run_rw("MATCH (s:Session {id: $sid}) DETACH DELETE s", {"sid": sid})
    await db.run_rw("MATCH (h:Handoff {session_id: $sid}) DETACH DELETE h", {"sid": sid})
    await db.run_rw(
        "MATCH (u:User {id: $uid}) "
        "CREATE (s:Session {id: $sid, user_id: $uid, status: 'OPEN', current_agent: 'agent-triage', started_at: $ts, msg_count: 0}) "
        "CREATE (u)-[:HAD_SESSION]->(s)",
        {"uid": uid, "sid": sid, "ts": now()},
    )
    # Ensure Priya has active seed facts
    await db.run_rw(
        "MATCH (u:User {id: $uid})-[:HAS_FACT]->(f:Fact) WHERE NOT (f.id IN $seed_ids) DETACH DELETE f",
        {
            "uid": uid,
            "seed_ids": ["fact-p-plan", "fact-p-channel", "fact-p-channel-old", "fact-p-city"],
        },
    )
    await db.run_rw("MATCH (f:Fact {id: 'fact-p-city'}) SET f.status = 'ACTIVE', f.object = 'Mumbai', f.valid_to = null")
    await db.run_rw("MATCH (f:Fact {id: 'fact-p-channel'}) SET f.status = 'ACTIVE', f.object = 'email', f.valid_to = null")

    ctx = MemoryContext(tenant_id="acme", user_id=uid, agent_id="agent-triage", session_id=sid)
    bus = EventBus()
    await run_turn(ctx, "Hello, my card shows a duplicate charge again on invoice INV-1042.", bus=bus)

    event_types = [e.type for e in bus.events]
    assert event_types[-1] == "final"

    # Check agent_active transitions
    active_events = [e for e in bus.events if e.type == "agent_active"]
    assert len(active_events) >= 2
    assert active_events[0].data["agent_id"] == "agent-triage"
    assert active_events[1].data["agent_id"] == "agent-billing"

    # Check handoff progression
    handoff_events = [e for e in bus.events if e.type == "handoff"]
    statuses = [e.data["status"] for e in handoff_events]
    assert "PENDING" in statuses
    assert "ACCEPTED" in statuses
    assert "COMPLETED" in statuses

    # Check session graph state: current_agent updated to agent-billing
    sess_res = await db.run_ro(
        "MATCH (s:Session {id: $sid}) RETURN s.current_agent",
        {"sid": sid},
    )
    assert sess_res[0][0] == "agent-billing"

    await db.run_rw("MATCH (e:Episode) WHERE e.id STARTS WITH 'ep-sess-' DETACH DELETE e")


@pytest.mark.asyncio
async def test_crew_subsequent_turn_routes_to_specialist():
    """Verify that after handoff acceptance, subsequent turns route to current_agent (specialist)."""
    db = await get_tenant_db("acme")
    sid = "sess-test-crew-persist"
    uid = "user-priya"

    # Create session already with agent-billing as current_agent
    await db.run_rw("MATCH (s:Session {id: $sid}) DETACH DELETE s", {"sid": sid})
    await db.run_rw(
        "MATCH (u:User {id: $uid}) "
        "CREATE (s:Session {id: $sid, user_id: $uid, status: 'OPEN', current_agent: 'agent-billing', started_at: $ts, msg_count: 0}) "
        "CREATE (u)-[:HAD_SESSION]->(s)",
        {"uid": uid, "sid": sid, "ts": now()},
    )

    ctx = MemoryContext(tenant_id="acme", user_id=uid, agent_id="agent-billing", session_id=sid)
    bus = EventBus()
    await run_turn(ctx, "Thanks for the update!", bus=bus)

    assert bus.events[-1].type == "final"
    active_events = [e for e in bus.events if e.type == "agent_active"]
    assert active_events[0].data["agent_id"] == "agent-billing"


@pytest.mark.asyncio
async def test_crew_single_turn_no_handoff():
    """Verify that a single turn without handoffs closes cleanly."""
    db = await get_tenant_db("acme")
    sid = "sess-test-crew-fact"
    uid = "user-priya"

    await db.run_rw("MATCH (s:Session {id: $sid}) DETACH DELETE s", {"sid": sid})
    await db.run_rw(
        "MATCH (u:User {id: $uid}) "
        "CREATE (s:Session {id: $sid, user_id: $uid, status: 'OPEN', current_agent: 'agent-triage', started_at: $ts, msg_count: 0}) "
        "CREATE (u)-[:HAD_SESSION]->(s)",
        {"uid": uid, "sid": sid, "ts": now()},
    )
    await db.run_rw(
        "MATCH (u:User {id: $uid})-[:HAS_FACT]->(f:Fact) WHERE NOT (f.id IN $seed_ids) DETACH DELETE f",
        {
            "uid": uid,
            "seed_ids": ["fact-p-plan", "fact-p-channel", "fact-p-channel-old", "fact-p-city"],
        },
    )

    ctx = MemoryContext(tenant_id="acme", user_id=uid, agent_id="agent-triage", session_id=sid)
    bus = EventBus()
    await run_turn(ctx, "By the way, I moved to Pune and I prefer chat now.", bus=bus)

    assert bus.events[-1].type == "final"
    handoff_events = [e for e in bus.events if e.type == "handoff"]
    assert len(handoff_events) == 0

    fact_events = [e for e in bus.events if e.type == "fact_update"]
    assert len(fact_events) == 2

    await db.run_rw("MATCH (e:Episode) WHERE e.id STARTS WITH 'ep-sess-' DETACH DELETE e")
