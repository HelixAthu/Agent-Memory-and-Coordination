"""Tests for live agent turn loop using scripted FakeSession simulating turns."""

from __future__ import annotations

import pytest

from backend.agent_live import run_agent_turn
from backend.events import EventBus
from backend.llm.base import LLMTurn, ToolCall
from backend.llm.fake_client import FakeSession
from backend.mcp_bridge import MemoryContext
from memory_core.clock import now
from memory_core.db import get_tenant_db


async def _create_test_session(sid: str, uid: str = "user-priya") -> None:
    """Helper to create or reset an open test session in the acme graph."""
    db = await get_tenant_db("acme")
    await db.run_rw("MATCH (s:Session {id: $sid}) DETACH DELETE s", {"sid": sid})
    await db.run_rw(
        "MATCH (u:User {id: $uid}) "
        "CREATE (s:Session {id: $sid, user_id: $uid, status: 'OPEN', current_agent: 'agent-triage', started_at: $ts, msg_count: 0}) "
        "CREATE (u)-[:HAD_SESSION]->(s)",
        {"uid": uid, "sid": sid, "ts": now()},
    )


@pytest.mark.asyncio
async def test_ten_call_cap_aborts():
    """Verify that exceeding 10 tool calls in a turn emits an unrecoverable error and halts."""
    sid = "sess-live-test-cap"
    await _create_test_session(sid)
    ctx = MemoryContext(
        tenant_id="acme",
        user_id="user-priya",
        agent_id="agent-triage",
        session_id=sid,
    )
    bus = EventBus()

    # 11 distinct tool calls
    calls = [
        ToolCall(id=f"c-{i}", name="get_user_profile", args={"dummy": i})
        for i in range(11)
    ]
    scripted = [LLMTurn(text="Checking profile multiple times", tool_calls=calls)]
    fake_session = FakeSession(scripted_turns=scripted)

    await run_agent_turn(
        ctx=ctx,
        role="triage",
        agent_name="agent-triage",
        input_text="Check my profile",
        bus=bus,
        session=fake_session,
    )

    error_events = [e for e in bus.events if e.type == "error"]
    assert len(error_events) == 1
    assert "Call limit exceeded" in error_events[0].data["message"]
    assert error_events[0].data["recoverable"] is False


@pytest.mark.asyncio
async def test_repeated_call_abort():
    """Verify that repeating the exact same tool call more than twice aborts the turn."""
    sid = "sess-live-test-repeat"
    await _create_test_session(sid)
    ctx = MemoryContext(
        tenant_id="acme",
        user_id="user-priya",
        agent_id="agent-triage",
        session_id=sid,
    )
    bus = EventBus()

    # 3 identical tool calls with same name and arguments
    call = ToolCall(id="c-rep", name="get_user_profile", args={})
    scripted = [
        LLMTurn(text="Calling profile 1", tool_calls=[call]),
        LLMTurn(text="Calling profile 2", tool_calls=[call]),
        LLMTurn(text="Calling profile 3", tool_calls=[call]),
    ]
    fake_session = FakeSession(scripted_turns=scripted)

    await run_agent_turn(
        ctx=ctx,
        role="triage",
        agent_name="agent-triage",
        input_text="Repeat call",
        bus=bus,
        session=fake_session,
    )

    error_events = [e for e in bus.events if e.type == "error"]
    assert len(error_events) >= 1
    assert "Repeated tool call aborted" in error_events[0].data["message"]
    assert error_events[0].data["recoverable"] is False


@pytest.mark.asyncio
async def test_tool_errors_fed_back_with_is_error():
    """Verify that tool errors are fed back as ToolResult(is_error=True) without crashing."""
    sid = "sess-live-test-err"
    await _create_test_session(sid)
    ctx = MemoryContext(
        tenant_id="acme",
        user_id="user-priya",
        agent_id="agent-triage",
        session_id=sid,
    )
    bus = EventBus()

    bad_call = ToolCall(id="call-err", name="remember_fact", args={"predicate": "invalid_pred", "object": "val"})
    scripted = [
        LLMTurn(text="Attempting invalid fact", tool_calls=[bad_call]),
        LLMTurn(text="Understood the error", tool_calls=[]),
    ]
    fake_session = FakeSession(scripted_turns=scripted)

    await run_agent_turn(
        ctx=ctx,
        role="triage",
        agent_name="agent-triage",
        input_text="Update fact",
        bus=bus,
        session=fake_session,
    )

    assert len(fake_session.received_results) == 1
    first_result = fake_session.received_results[0][0]
    assert first_result.call_id == "call-err"
    assert first_result.is_error is True
    assert "error" in first_result.content or not first_result.content.get("ok", True)


@pytest.mark.asyncio
async def test_all_agent_text_saved_as_messages():
    """Verify that all assistant turn text is persisted to session history and emitted."""
    sid = "sess-live-test-msgs"
    await _create_test_session(sid)
    ctx = MemoryContext(
        tenant_id="acme",
        user_id="user-priya",
        agent_id="agent-triage",
        session_id=sid,
    )
    bus = EventBus()

    call = ToolCall(id="c-prof", name="get_user_profile", args={})
    scripted = [
        LLMTurn(text="I am checking your records now.", tool_calls=[call]),
        LLMTurn(text="Everything is up to date, thank you!", tool_calls=[]),
    ]
    fake_session = FakeSession(scripted_turns=scripted)

    result = await run_agent_turn(
        ctx=ctx,
        role="triage",
        agent_name="agent-triage",
        input_text="Status check",
        bus=bus,
        session=fake_session,
    )

    assert len(result.messages) == 2
    msg_events = [e for e in bus.events if e.type == "message"]
    assert len(msg_events) == 2
    assert msg_events[0].data["text"] == "I am checking your records now."
    assert msg_events[1].data["text"] == "Everything is up to date, thank you!"


@pytest.mark.asyncio
async def test_specialised_events_built_from_envelope():
    """Verify that specialised events (fact_update, recall_result, handoff) are generated."""
    db = await get_tenant_db("acme")
    sid = "sess-live-test-specialised"
    uid = "user-priya"
    await _create_test_session(sid, uid)

    # Ensure active seed fact for city
    await db.run_rw(
        "MATCH (u:User {id: $uid})-[:HAS_FACT]->(f:Fact) WHERE NOT (f.id IN $seed_ids) DETACH DELETE f",
        {
            "uid": uid,
            "seed_ids": ["fact-p-plan", "fact-p-channel", "fact-p-channel-old", "fact-p-city"],
        },
    )
    await db.run_rw("MATCH (f:Fact {id: 'fact-p-city'}) SET f.status = 'ACTIVE', f.object = 'Mumbai', f.valid_to = null")

    ctx = MemoryContext(tenant_id="acme", user_id=uid, agent_id="agent-triage", session_id=sid)
    bus = EventBus()

    call_fact = ToolCall(id="c-f", name="remember_fact", args={"predicate": "city", "object": "Pune"})
    scripted = [
        LLMTurn(text="Updating your city to Pune.", tool_calls=[call_fact]),
        LLMTurn(text="Done updating.", tool_calls=[]),
    ]
    fake_session = FakeSession(scripted_turns=scripted)

    await run_agent_turn(
        ctx=ctx,
        role="triage",
        agent_name="agent-triage",
        input_text="I moved to Pune",
        bus=bus,
        session=fake_session,
    )

    fact_events = [e for e in bus.events if e.type == "fact_update"]
    assert len(fact_events) == 1
    assert fact_events[0].data["predicate"] == "city"
    assert fact_events[0].data["object"] == "Pune"
    assert fact_events[0].data["action"] == "superseded"
