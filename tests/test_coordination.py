"""Unit and golden concurrency tests for coordination, tasks, routing, handoffs, and CAS state (G7, G8, G11, G12)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from memory_core.coordination import (
    accept_handoff,
    claim_next,
    claim_task,
    complete_handoff,
    create_handoff,
    get_state,
    route,
    set_state,
)
from memory_core.db import TenantDB, get_tenant_db
from memory_core.errors import ConflictError, ForbiddenError, NotFoundError
from memory_core.history import append_message, create_session
from seed.seed import seed_tenant


@pytest.mark.asyncio
async def test_g7_routing() -> None:
    """Verify G7: topic-based routing returns correct specialists and rejects unknown topics."""
    await seed_tenant("acme", reset=False)

    assert await route("acme", "topic-billing") == ["agent-billing"]
    assert await route("acme", "topic-refunds") == ["agent-billing"]
    assert await route("acme", "topic-vpn") == ["agent-tech"]
    assert await route("acme", "topic-login") == ["agent-tech"]
    assert await route("acme", "topic-general") == ["agent-triage"]

    # Unknown topic returns NotFoundError
    with pytest.raises(NotFoundError):
        await route("acme", "topic-unknown")


@pytest.mark.asyncio
async def test_g8_handoff_protocol_and_concurrency() -> None:
    """Verify G8: handoff carries exactly 8 bundle elements and atomic accept enforces authorization and concurrency."""
    await seed_tenant("acme", reset=True)
    db: TenantDB = await get_tenant_db("acme")

    session_id = "sess-demo-continuity"
    await create_session("acme", "user-priya", "agent-triage", session_id=session_id)
    await append_message("acme", session_id, "user", "I was charged twice for invoice INV-1042.")
    await append_message("acme", session_id, "agent", "Sorry about that, let me connect you with Billing.", "agent-triage")

    # 1. Create handoff
    hof = await create_handoff(
        tenant_id="acme",
        session_id=session_id,
        from_agent="agent-triage",
        to_agent="agent-billing",
        reason="Billing inquiry handoff",
        now_ts=1792108800,
    )

    hid: str = hof["handoff_id"]
    carries = hof["carries"]
    assert carries["fact"] == 3
    assert carries["episode"] == 2
    assert carries["procedure"] == 1
    assert carries["message"] == 2
    assert hof["carries_total"] == 8

    # 2. Unauthorized agent acceptance returns FORBIDDEN
    with pytest.raises(ForbiddenError):
        await accept_handoff("acme", hid, agent_id="agent-tech")

    # 3. Authorized agent acceptance succeeds
    acc_res = await accept_handoff("acme", hid, agent_id="agent-billing")
    assert acc_res["handoff_id"] == hid
    assert acc_res["session_id"] == session_id

    # Verify session active agent updated
    curr_agent_res: list[Any] = await db.run_ro(
        "MATCH (s:Session {id: $sid}) RETURN s.current_agent",
        {"sid": session_id},
    )
    assert curr_agent_res[0][0] == "agent-billing"

    # 4. Second accept returns CONFLICT
    with pytest.raises(ConflictError):
        await accept_handoff("acme", hid, agent_id="agent-billing")

    # 5. Complete handoff succeeds
    await complete_handoff(
        tenant_id="acme",
        handoff_id=hid,
        agent_id="agent-billing",
        outcome="resolved",
        summary="Refund processed successfully",
    )

    # 6. Test 10 concurrent accepts on a fresh PENDING handoff: exactly 1 success and 9 CONFLICT
    hof2 = await create_handoff(
        tenant_id="acme",
        session_id=session_id,
        from_agent="agent-triage",
        to_agent="agent-billing",
        reason="Concurrent acceptance test",
    )
    hid2: str = hof2["handoff_id"]

    # Re-open session status temporarily for second handoff if needed
    await db.run_rw("MATCH (h:Handoff {id: $hid}) SET h.status = 'PENDING'", {"hid": hid2})

    async def try_accept() -> str:
        try:
            await accept_handoff("acme", hid2, agent_id="agent-billing")
            return "SUCCESS"
        except ConflictError:
            return "CONFLICT"

    results: list[str] = await asyncio.gather(*[try_accept() for _ in range(10)])
    success_count: int = results.count("SUCCESS")
    conflict_count: int = results.count("CONFLICT")
    assert success_count == 1, f"Expected 1 success, got {success_count}"
    assert conflict_count == 9, f"Expected 9 conflicts, got {conflict_count}"


@pytest.mark.asyncio
async def test_g11_tasks() -> None:
    """Verify G11: task claiming state machine, version increment, and claim_next."""
    await seed_tenant("acme", reset=True)

    # 1. Claim task-001 succeeds with version 2
    v1: int = await claim_task("acme", "task-001", "agent-tech")
    assert v1 == 2

    # 2. Second claim of task-001 returns CONFLICT
    with pytest.raises(ConflictError):
        await claim_task("acme", "task-001", "agent-billing")

    # 3. claim_next with task-001 claimed and task-002 DONE returns NotFoundError
    with pytest.raises(NotFoundError):
        await claim_next("acme", "agent-tech")


@pytest.mark.asyncio
async def test_g12_shared_state_cas_and_concurrent_increments() -> None:
    """Verify G12: optimistic CAS state transitions and 20 concurrent CAS increments."""
    await seed_tenant("acme", reset=False)

    sid = "sess-p1"
    key = "counter"

    # Clean up prior test state if any
    db: TenantDB = await get_tenant_db("acme")
    await db.run_rw("MATCH (e:StateEntry {id: $eid}) DETACH DELETE e", {"eid": f"st-{sid}-{key}"})

    # 1. Create initial state with version 0 -> 1
    v1: int = await set_state("acme", sid, key, "a", expected_version=0, agent_id="agent-triage")
    assert v1 == 1

    # 2. Update to "b" with version 1 -> 2
    v2: int = await set_state("acme", sid, key, "b", expected_version=1, agent_id="agent-triage")
    assert v2 == 2

    # 3. Mismatched expected_version returns CONFLICT with current_version=2
    with pytest.raises(ConflictError) as exc_info:
        await set_state("acme", sid, key, "c", expected_version=1, agent_id="agent-triage")
    assert exc_info.value.current_version == 2

    # 4. 20 concurrent CAS increments ending at exactly version 20
    counter_key = "atomic_count"
    await db.run_rw("MATCH (e:StateEntry {id: $eid}) DETACH DELETE e", {"eid": f"st-{sid}-{counter_key}"})
    await set_state("acme", sid, counter_key, "0", expected_version=0, agent_id="agent-triage")

    async def increment_cas() -> None:
        for _ in range(50):
            state = await get_state("acme", sid, counter_key)
            cur_val = int(state["value"])
            cur_ver = int(state["version"])
            try:
                await set_state(
                    tenant_id="acme",
                    session_id=sid,
                    key=counter_key,
                    value=str(cur_val + 1),
                    expected_version=cur_ver,
                    agent_id="agent-worker",
                )
                return
            except ConflictError:
                await asyncio.sleep(0.01)
        raise RuntimeError("Exceeded retry limit in CAS increment")

    await asyncio.gather(*[increment_cas() for _ in range(20)])

    final_state = await get_state("acme", sid, counter_key)
    assert int(final_state["value"]) == 20
    # version incremented 20 times starting from initial version 1 -> version 21
    assert int(final_state["version"]) == 21
