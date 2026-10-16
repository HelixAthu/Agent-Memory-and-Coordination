"""End-to-end integration tests for REST API, authentication, SSE streams, and persistence."""

from __future__ import annotations

import json
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from memory_core.db import get_tenant_db


@pytest.mark.asyncio
async def test_auth_missing_key_returns_401():
    """Verify that requests without X-API-Key return 401 Unauthorized."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/t/acme/users")
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_auth_tenant_mismatch_returns_403():
    """Verify that providing an acme key on a globex route returns 403 Forbidden."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/t/globex/users",
            headers={"X-API-Key": "acme-demo-key"},
        )
        assert res.status_code == 403


@pytest.mark.asyncio
async def test_e2e_continuity_scenario_and_sse_stream():
    """Verify end-to-end continuity scenario creation, event streaming, and message persistence."""
    # Ensure clean seed state for Priya before running scenario
    db = await get_tenant_db("acme")
    await db.run_rw("MATCH (e:Episode) WHERE e.id STARTS WITH 'ep-sess-' DETACH DELETE e")
    await db.run_rw(
        "MATCH (u:User {id: $uid})-[:HAS_FACT]->(f:Fact) WHERE NOT (f.id IN $seed_ids) DETACH DELETE f",
        {
            "uid": "user-priya",
            "seed_ids": ["fact-p-plan", "fact-p-channel", "fact-p-channel-old", "fact-p-city"],
        },
    )
    await db.run_rw("MATCH (f:Fact {id: 'fact-p-city'}) SET f.status = 'ACTIVE', f.object = 'Mumbai', f.valid_to = null")
    await db.run_rw("MATCH (f:Fact {id: 'fact-p-channel'}) SET f.status = 'ACTIVE', f.object = 'email', f.valid_to = null")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Boot continuity scenario
        res_session = await client.post(
            "/t/acme/sessions",
            headers={"X-API-Key": "acme-demo-key"},
            json={"user_id": "user-priya", "scenario": "continuity"},
        )
        assert res_session.status_code == 200
        sid = res_session.json()["session_id"]
        assert sid == "sess-demo-continuity"

        # 2. Consume SSE stream until final or timeout
        received_events: list[dict[str, Any]] = []
        async with client.stream(
            "GET",
            f"/t/acme/sessions/{sid}/stream",
            headers={"X-API-Key": "acme-demo-key"},
            timeout=15.0,
        ) as stream:
            assert stream.status_code == 200
            async for line in stream.aiter_lines():
                if line.startswith("data:"):
                    raw_data = line[len("data:"):].strip()
                    if raw_data:
                        try:
                            evt = json.loads(raw_data)
                            received_events.append(evt)
                            if evt.get("type") == "final":
                                break
                        except json.JSONDecodeError:
                            pass

        event_types = [e.get("type") for e in received_events]
        assert "session_started" in event_types
        assert "agent_active" in event_types
        assert "handoff" in event_types
        assert "session_closed" in event_types
        assert "final" in event_types

        # Verify handoff COMPLETED was emitted
        completed_handoffs = [
            e for e in received_events
            if e.get("type") == "handoff" and e.get("data", {}).get("status") == "COMPLETED"
        ]
        assert len(completed_handoffs) >= 1

        # 3. Retrieve persistent messages
        res_msgs = await client.get(
            f"/t/acme/sessions/{sid}/messages",
            headers={"X-API-Key": "acme-demo-key"},
        )
        assert res_msgs.status_code == 200
        messages = res_msgs.json()
        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "agent"
        assert messages[2]["role"] == "agent"


@pytest.mark.asyncio
async def test_restart_persistence_and_episode_present():
    """Verify persistence across fresh client instances: recall top-1 and created episode."""
    # Build a fresh transport and client from scratch against the same FalkorDB
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Check episodes endpoint for Priya
        res_episodes = await client.get(
            "/t/acme/users/user-priya/episodes",
            headers={"X-API-Key": "acme-demo-key"},
        )
        assert res_episodes.status_code == 200
        episodes = res_episodes.json()
        ep_ids = [e["id"] for e in episodes]
        assert "ep-sess-demo-continuity" in ep_ids

        # Check recall via core
        from memory_core.recall import recall
        rec = await recall(
            tenant_id="acme",
            user_id="user-priya",
            query="Hello, my card shows a duplicate charge again on invoice INV-1042.",
            k=3,
        )
        assert len(rec["episodes"]) >= 1
        rec_ids = [e["id"] for e in rec["episodes"]]
        assert "ep-p1" in rec_ids
        assert "ep-sess-demo-continuity" in rec_ids

        db = await get_tenant_db("acme")
        await db.run_rw("MATCH (e:Episode) WHERE e.id STARTS WITH 'ep-sess-' DETACH DELETE e")


@pytest.mark.asyncio
async def test_isolation_check_endpoint():
    """Verify that /t/acme/isolation-check runs G13 invariants and returns all passed."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/t/acme/isolation-check",
            headers={"X-API-Key": "acme-demo-key"},
        )
        assert res.status_code == 200
        checks = res.json()
        assert len(checks) >= 4
        for c in checks:
            assert c["passed"] is True, f"Isolation check failed: {c['name']} - {c['detail']}"


@pytest.mark.asyncio
async def test_no_response_body_contains_embedding():
    """Verify that no graph or entity response body ever exposes the key 'embedding'."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        endpoints = [
            "/t/acme/users/user-priya/graph",
            "/t/acme/users/user-priya/facts?include_history=true",
            "/t/acme/users/user-priya/episodes",
            "/t/acme/procedures",
            "/t/acme/tasks",
            "/t/acme/handoffs",
        ]
        for ep in endpoints:
            res = await client.get(ep, headers={"X-API-Key": "acme-demo-key"})
            assert res.status_code == 200
            assert "embedding" not in res.text, f"Endpoint {ep} leaked embedding property!"
