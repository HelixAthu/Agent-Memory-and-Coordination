"""Tests verifying scripted mock scenarios, bridge context injection, and goldens G2, G4, G8, G9, G10."""

from __future__ import annotations

import pytest

from backend.agent_mock import run_mock_scenario
from backend.events import EventBus
from backend.mcp_bridge import MCPBridge, MemoryContext
from memory_core.db import get_tenant_db


@pytest.mark.asyncio
async def test_llm_visible_toolspecs_have_no_context_fields():
    """Verify that ToolSpecs produced by the bridge omit all four context fields."""
    bridge = MCPBridge()
    for role in ("triage", "specialist"):
        specs = await bridge.tools_for(role)
        assert len(specs) > 0
        for s in specs:
            props = s.input_schema.get("properties", {})
            required = s.input_schema.get("required", [])
            for field_name in ("tenant_id", "user_id", "agent_id", "session_id"):
                assert field_name not in props, f"{field_name} leaked in {s.name} properties"
                assert field_name not in required, f"{field_name} leaked in {s.name} required"


@pytest.mark.asyncio
async def test_bridge_drops_caller_context_args_and_emits_warning():
    """Verify that bridge drops context args supplied by caller and emits warning event (G13)."""
    bridge = MCPBridge()
    bus = EventBus()
    ctx = MemoryContext("acme", "user-priya", "agent-triage", "sess-test-warning")

    # Pass malicious or cross-tenant context fields in args
    bad_args = {
        "tenant_id": "globex",
        "user_id": "user-dana",
        "query": "invoice charge",
        "k": 3,
    }
    env = await bridge.call(ctx, "recall_memory", bad_args, bus=bus)
    assert env["ok"] is True

    warnings = [e for e in bus.events if e.type == "warning"]
    assert len(warnings) >= 1
    assert any("tenant_id" in w.data.get("message", "") for w in warnings)


@pytest.mark.asyncio
async def test_bridge_hides_non_allowlisted_tools():
    """Verify that the bridge hides non-allowlisted tools per agent role."""
    bridge = MCPBridge()
    triage_specs = await bridge.tools_for("triage")
    triage_names = {s.name for s in triage_specs}

    assert "accept_handoff" not in triage_names
    assert "complete_handoff" not in triage_names
    assert "claim_next_task" not in triage_names
    assert "get_user_profile" in triage_names


@pytest.mark.asyncio
async def test_continuity_scenario_goldens_g2_g8_g9():
    """Verify continuity mock scenario asserts G2, G8, G9 via events and graph reads."""
    bus = await run_mock_scenario("continuity")
    types = [e.type for e in bus.events]
    assert types[-1] == "final"

    # G2: first recall_result episode is ep-p1
    recall_events = [e for e in bus.events if e.type == "recall_result"]
    assert len(recall_events) == 1
    episodes = recall_events[0].data["episodes"]
    assert len(episodes) >= 1
    assert episodes[0]["id"] == "ep-p1"

    # G8: handoff carries exactly 8 elements with correct per-kind counts
    handoff_events = [e for e in bus.events if e.type == "handoff"]
    assert len(handoff_events) >= 1
    carries = handoff_events[0].data["carries"]
    assert carries["fact"] == 3
    assert carries["episode"] == 2
    assert carries["procedure"] == 1
    assert carries["message"] == 2
    assert sum(carries.values()) == 8

    # G9: session_closed produces episode ep-sess-demo-continuity with importance 0.8
    close_events = [e for e in bus.events if e.type == "session_closed"]
    assert len(close_events) == 1
    assert close_events[0].data["episode_id"] == "ep-sess-demo-continuity"
    assert close_events[0].data["importance"] == 0.8

    # Verify directly in the tenant graph
    db = await get_tenant_db("acme")
    ep_res = await db.run_ro(
        "MATCH (e:Episode {id: 'ep-sess-demo-continuity'}) "
        "RETURN e.status, e.importance",
    )
    assert len(ep_res) == 1
    assert ep_res[0][0] == "ACTIVE"
    assert round(float(ep_res[0][1]), 2) == 0.8

    # Check memory_visit node_ids all exist in the graph
    visit_events = [e for e in bus.events if e.type == "memory_visit"]
    for v in visit_events:
        for nid in v.data.get("node_ids", []):
            node_check = await db.run_ro("MATCH (n {id: $id}) RETURN count(n)", {"id": nid})
            assert int(node_check[0][0]) > 0, f"Node {nid} from memory_visit not found in graph"


@pytest.mark.asyncio
async def test_fact_update_scenario_golden_g4():
    """Verify fact_update mock scenario asserts G4 (supersession and single active fact)."""
    bus = await run_mock_scenario("fact_update")
    assert bus.events[-1].type == "final"

    fact_events = [e for e in bus.events if e.type == "fact_update"]
    assert len(fact_events) == 2
    city_event = next(e for e in fact_events if e.data["predicate"] == "city")
    assert city_event.data["object"] == "Pune"
    assert city_event.data["action"] == "superseded"

    # Direct graph assertion: exactly 1 active fact for city with object Pune
    db = await get_tenant_db("acme")
    city_res = await db.run_ro(
        "MATCH (u:User {id: 'user-priya'})-[:HAS_FACT]->(f:Fact {predicate: 'city', status: 'ACTIVE'}) "
        "RETURN f.object",
    )
    assert len(city_res) == 1
    assert str(city_res[0][0]) == "Pune"


@pytest.mark.asyncio
async def test_procedure_learning_scenario_golden_g10():
    """Verify procedure_learning mock scenario asserts G10 (promotion to ACTIVE)."""
    bus = await run_mock_scenario("procedure_learning")
    assert bus.events[-1].type == "final"

    # G10: close_session promotes proc-vpn-token-reset
    close_events = [e for e in bus.events if e.type == "session_closed"]
    assert len(close_events) == 1
    assert "proc-vpn-token-reset" in close_events[0].data["promoted"]

    # Direct graph assertion: procedure status is now ACTIVE
    db = await get_tenant_db("acme")
    proc_res = await db.run_ro(
        "MATCH (p:Procedure {id: 'proc-vpn-token-reset'}) RETURN p.status",
    )
    assert len(proc_res) == 1
    assert str(proc_res[0][0]) == "ACTIVE"
