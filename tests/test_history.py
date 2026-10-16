"""Unit and concurrency tests for session history and atomic message appending (G14)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from memory_core.db import TenantDB, get_tenant_db
from memory_core.errors import NotFoundError
from memory_core.history import append_message, create_session, get_messages
from seed.seed import seed_tenant


@pytest.mark.asyncio
async def test_session_creation_and_message_flow() -> None:
    """Test session creation, sequential message append, and chronological retrieval."""
    await seed_tenant("acme", reset=False)

    sid: str = await create_session(
        tenant_id="acme",
        user_id="user-priya",
        current_agent="agent-triage",
    )
    assert sid.startswith("sess-")

    # Nonexistent user raises NotFoundError
    with pytest.raises(NotFoundError):
        await create_session(
            tenant_id="acme",
            user_id="user-nonexistent",
            current_agent="agent-triage",
        )

    # Append sequential messages
    m1: dict[str, Any] = await append_message(
        tenant_id="acme",
        session_id=sid,
        role="user",
        text="Hello, I need help with my invoice.",
    )
    assert m1["seq"] == 1

    m2: dict[str, Any] = await append_message(
        tenant_id="acme",
        session_id=sid,
        role="agent",
        agent_id="agent-triage",
        text="I can assist with that. Looking into your account.",
    )
    assert m2["seq"] == 2

    # Verify retrieval
    msgs: list[dict[str, Any]] = await get_messages("acme", sid)
    assert len(msgs) == 2
    assert msgs[0]["seq"] == 1
    assert msgs[1]["seq"] == 2
    assert msgs[0]["text"] == "Hello, I need help with my invoice."
    assert msgs[1]["text"] == "I can assist with that. Looking into your account."


@pytest.mark.asyncio
async def test_g14_concurrent_message_append() -> None:
    """Verify G14: 3 concurrent append_message calls on a session produce sequential {5, 6, 7}."""
    # Reset and seed acme to known baseline (sess-p1 msg_count = 4)
    await seed_tenant("acme", reset=True)
    db: TenantDB = await get_tenant_db("acme")

    session_id: str = "sess-p1"

    # Launch 3 concurrent append_message calls
    coros = [
        append_message(
            tenant_id="acme",
            session_id=session_id,
            role="user",
            text=f"Concurrent message payload {i}",
        )
        for i in range(1, 4)
    ]
    results: list[dict[str, Any]] = await asyncio.gather(*coros)

    seq_set: set[int] = {r["seq"] for r in results}
    assert seq_set == {5, 6, 7}, f"Expected seqs {{5, 6, 7}}, got {seq_set}"

    # Verify the session has 7 messages
    msg_count_res: list[Any] = await db.run_ro(
        "MATCH (s:Session {id: $sid})-[:HAS_MESSAGE]->(m:Message) RETURN count(m)",
        {"sid": session_id},
    )
    assert msg_count_res[0][0] == 7, f"Expected 7 messages in session, got {msg_count_res[0][0]}"

    # Verify the full NEXT chain has 6 edges in strict sequence 1 -> 2 -> ... -> 7
    chain_res: list[Any] = await db.run_ro(
        "MATCH (s:Session {id: $sid})-[:HAS_MESSAGE]->(m1:Message)-[:NEXT]->(m2:Message) "
        "RETURN m1.seq AS s1, m2.seq AS s2 ORDER BY s1",
        {"sid": session_id},
    )
    assert len(chain_res) == 6, f"Expected 6 NEXT links, got {len(chain_res)}"
    for row in chain_res:
        assert row[1] == row[0] + 1, f"Chain discontinuity: {row[0]} -> {row[1]}"
