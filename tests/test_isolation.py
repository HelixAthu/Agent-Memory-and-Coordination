"""Tests verifying multi-tenant and cross-user isolation and authorization (G13)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from memory_mcp.server import mcp


@pytest.mark.asyncio
async def test_agent_role_forbidden_call():
    """Verify agent-triage (role triage) calling accept_handoff returns FORBIDDEN."""
    res = await mcp.call_tool(
        "accept_handoff",
        {
            "tenant_id": "acme",
            "user_id": "user-priya",
            "agent_id": "agent-triage",
            "session_id": "sess-demo-continuity",
            "handoff_id": "ho-fake",
        },
    )
    env: dict[str, Any] = json.loads(res.content[0].text)
    assert env["ok"] is False
    assert env["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_invalid_tenant_identifier():
    """Verify malicious or unconfigured tenant_id yields INVALID_INPUT."""
    res = await mcp.call_tool(
        "recall_memory",
        {
            "tenant_id": "acme; DROP",
            "user_id": "user-priya",
            "agent_id": "agent-triage",
            "session_id": "sess-demo-continuity",
            "query": "invoice check",
            "k": 3,
        },
    )
    env: dict[str, Any] = json.loads(res.content[0].text)
    assert env["ok"] is False
    assert env["error"]["code"] == "INVALID_INPUT"


@pytest.mark.asyncio
async def test_session_ownership_mismatch():
    """Verify accessing another user's session yields FORBIDDEN."""
    # sess-p1 belongs to user-priya
    res = await mcp.call_tool(
        "recall_memory",
        {
            "tenant_id": "acme",
            "user_id": "user-rahul",
            "agent_id": "agent-triage",
            "session_id": "sess-p1",
            "query": "vpn issue",
            "k": 3,
        },
    )
    env: dict[str, Any] = json.loads(res.content[0].text)
    assert env["ok"] is False
    assert env["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_cross_user_recall_isolation():
    """Verify recall executed for user-rahul returns no user-priya data."""
    res = await mcp.call_tool(
        "recall_memory",
        {
            "tenant_id": "acme",
            "user_id": "user-rahul",
            "agent_id": "agent-triage",
            "session_id": "sess-demo-vpn",
            "query": "invoice INV-1042 duplicate card charge",
            "k": 5,
        },
    )
    env: dict[str, Any] = json.loads(res.content[0].text)
    assert env["ok"] is True
    episodes = env["data"]["episodes"]
    # No episode belonging to priya (ep-p1, ep-p2, ep-p3) may appear
    for ep in episodes:
        assert not ep["id"].startswith("ep-p")

    # Facts returned must belong only to rahul
    facts = env["data"]["facts"]
    for f in facts:
        assert not f["id"].startswith("fact-p")
