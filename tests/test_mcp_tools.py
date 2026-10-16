"""Tests verifying MCP tools execution over stdio client and concurrency."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from memory_core.history import append_message, create_session


@pytest.fixture
def mcp_server_params() -> StdioServerParameters:
    """Server parameters launching memory_mcp.server over stdio."""
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "memory_mcp.server"],
        env=None,
    )


@pytest.mark.asyncio
async def test_mcp_tools_stdio_lifecycle_and_execution(mcp_server_params: StdioServerParameters):
    """Verify tool listing, documentation contracts, and execution across tools over stdio."""
    # Ensure active session exists for priya
    try:
        await create_session(
            "acme", "user-priya", "agent-triage", session_id="sess-demo-continuity"
        )
    except Exception:
        pass
    try:
        await append_message(
            "acme",
            "sess-demo-continuity",
            "user",
            "Hello, duplicate charge on invoice INV-1042",
        )
    except Exception:
        pass

    async with stdio_client(mcp_server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. List tools and verify documentation contracts
            tools_res = await session.list_tools()
            tools = tools_res.tools
            assert len(tools) == 16
            for tool in tools:
                assert tool.description is not None
                assert "Use when:" in tool.description
                assert "Do not use when:" in tool.description

            # 2. get_user_profile
            res = await session.call_tool(
                "get_user_profile",
                {
                    "tenant_id": "acme",
                    "user_id": "user-priya",
                    "agent_id": "agent-triage",
                    "session_id": "sess-demo-continuity",
                    "include_history": True,
                },
            )
            env: dict[str, Any] = json.loads(res.content[0].text)
            assert env["ok"] is True
            assert "facts" in env["data"]
            assert any(f["predicate"] == "plan" for f in env["data"]["facts"])

            # 3. recall_memory
            res = await session.call_tool(
                "recall_memory",
                {
                    "tenant_id": "acme",
                    "user_id": "user-priya",
                    "agent_id": "agent-triage",
                    "session_id": "sess-demo-continuity",
                    "query": "duplicate charge on invoice INV-1042",
                    "k": 3,
                },
            )
            env = json.loads(res.content[0].text)
            assert env["ok"] is True
            assert len(env["data"]["episodes"]) > 0

            # 4. find_procedure
            res = await session.call_tool(
                "find_procedure",
                {
                    "tenant_id": "acme",
                    "user_id": "user-priya",
                    "agent_id": "agent-triage",
                    "session_id": "sess-demo-continuity",
                    "situation": "duplicate charge on invoice",
                    "include_candidates": True,
                },
            )
            env = json.loads(res.content[0].text)
            assert env["ok"] is True
            assert len(env["data"]["procedures"]) > 0

            # 5. route_to_specialist
            res = await session.call_tool(
                "route_to_specialist",
                {
                    "tenant_id": "acme",
                    "user_id": "user-priya",
                    "agent_id": "agent-triage",
                    "session_id": "sess-demo-continuity",
                    "topic_id": "topic-billing",
                },
            )
            env = json.loads(res.content[0].text)
            assert env["ok"] is True
            assert any(c["id"] == "agent-billing" for c in env["data"]["candidates"])

            # 6. create_handoff
            res = await session.call_tool(
                "create_handoff",
                {
                    "tenant_id": "acme",
                    "user_id": "user-priya",
                    "agent_id": "agent-triage",
                    "session_id": "sess-demo-continuity",
                    "to_agent_id": "agent-billing",
                    "reason": "Customer needs billing dispute resolution",
                },
            )
            env = json.loads(res.content[0].text)
            assert env["ok"] is True
            handoff_id = env["data"]["handoff_id"]
            assert handoff_id.startswith("hof-")

            # 7. get_pending_handoffs
            res = await session.call_tool(
                "get_pending_handoffs",
                {
                    "tenant_id": "acme",
                    "user_id": "user-priya",
                    "agent_id": "agent-billing",
                    "session_id": "sess-demo-continuity",
                },
            )
            env = json.loads(res.content[0].text)
            assert env["ok"] is True
            assert any(h["id"] == handoff_id for h in env["data"]["handoffs"])

            # 8. accept_handoff
            res = await session.call_tool(
                "accept_handoff",
                {
                    "tenant_id": "acme",
                    "user_id": "user-priya",
                    "agent_id": "agent-billing",
                    "session_id": "sess-demo-continuity",
                    "handoff_id": handoff_id,
                },
            )
            env = json.loads(res.content[0].text)
            assert env["ok"] is True
            assert env["data"]["status"] == "ACCEPTED"

            # 9. record_procedure_outcome
            res = await session.call_tool(
                "record_procedure_outcome",
                {
                    "tenant_id": "acme",
                    "user_id": "user-priya",
                    "agent_id": "agent-billing",
                    "session_id": "sess-demo-continuity",
                    "procedure_id": "proc-dup-charge-refund",
                    "outcome": "success",
                },
            )
            env = json.loads(res.content[0].text)
            assert env["ok"] is True
            assert env["data"]["outcome"] == "success"

            # 10. complete_handoff
            res = await session.call_tool(
                "complete_handoff",
                {
                    "tenant_id": "acme",
                    "user_id": "user-priya",
                    "agent_id": "agent-billing",
                    "session_id": "sess-demo-continuity",
                    "handoff_id": handoff_id,
                    "outcome": "resolved",
                    "summary": "Verified charges and issued refund",
                },
            )
            env = json.loads(res.content[0].text)
            assert env["ok"] is True
            assert env["data"]["status"] == "COMPLETED"

            # 11. create_task
            res = await session.call_tool(
                "create_task",
                {
                    "tenant_id": "acme",
                    "user_id": "user-priya",
                    "agent_id": "agent-triage",
                    "session_id": "sess-demo-continuity",
                    "title": "Audit recurring invoice anomalies",
                    "priority": 3,
                },
            )
            env = json.loads(res.content[0].text)
            assert env["ok"] is True
            task_id = env["data"]["task_id"]
            assert task_id.startswith("task-")

            # 12. claim_next_task
            res = await session.call_tool(
                "claim_next_task",
                {
                    "tenant_id": "acme",
                    "user_id": "user-priya",
                    "agent_id": "agent-billing",
                    "session_id": "sess-demo-continuity",
                },
            )
            env = json.loads(res.content[0].text)
            assert env["ok"] is True
            assert env["data"]["task_id"] is not None

            # 13. complete_task
            res = await session.call_tool(
                "complete_task",
                {
                    "tenant_id": "acme",
                    "user_id": "user-priya",
                    "agent_id": "agent-billing",
                    "session_id": "sess-demo-continuity",
                    "task_id": env["data"]["task_id"],
                },
            )
            env = json.loads(res.content[0].text)
            assert env["ok"] is True
            assert env["data"]["status"] == "DONE"

            # 14. set_shared_state & get_shared_state
            res = await session.call_tool(
                "set_shared_state",
                {
                    "tenant_id": "acme",
                    "user_id": "user-priya",
                    "agent_id": "agent-billing",
                    "session_id": "sess-demo-continuity",
                    "key": "mcp_shared_counter",
                    "value": "100",
                    "expected_version": 0,
                },
            )
            env = json.loads(res.content[0].text)
            assert env["ok"] is True

            res = await session.call_tool(
                "get_shared_state",
                {
                    "tenant_id": "acme",
                    "user_id": "user-priya",
                    "agent_id": "agent-billing",
                    "session_id": "sess-demo-continuity",
                    "key": "mcp_shared_counter",
                },
            )
            env = json.loads(res.content[0].text)
            assert env["ok"] is True
            assert env["data"]["value"] == "100"

            # 15. remember_fact
            res = await session.call_tool(
                "remember_fact",
                {
                    "tenant_id": "acme",
                    "user_id": "user-priya",
                    "agent_id": "agent-triage",
                    "session_id": "sess-demo-continuity",
                    "predicate": "city",
                    "object": "Pune",
                    "confidence": 0.85,
                },
            )
            env = json.loads(res.content[0].text)
            assert env["ok"] is True
            assert env["data"]["action"] in ("created", "superseded", "reinforced")

            # 16. close_session
            res = await session.call_tool(
                "close_session",
                {
                    "tenant_id": "acme",
                    "user_id": "user-priya",
                    "agent_id": "agent-billing",
                    "session_id": "sess-demo-continuity",
                    "outcome": "resolved",
                    "summary": "Session concluded successfully",
                },
            )
            env = json.loads(res.content[0].text)
            assert env["ok"] is True


@pytest.mark.asyncio
async def test_20_parallel_recall_memory_calls(mcp_server_params: StdioServerParameters):
    """Verify that 20 concurrent recall_memory calls over a single MCP session all succeed."""
    async with stdio_client(mcp_server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            async def call_recall(idx: int) -> dict[str, Any]:
                res = await session.call_tool(
                    "recall_memory",
                    {
                        "tenant_id": "acme",
                        "user_id": "user-priya",
                        "agent_id": "agent-triage",
                        "session_id": "sess-demo-continuity",
                        "query": f"invoice query variation {idx}",
                        "k": 3,
                    },
                )
                return json.loads(res.content[0].text)

            tasks = [call_recall(i) for i in range(20)]
            results = await asyncio.gather(*tasks)

            assert len(results) == 20
            for r in results:
                assert r["ok"] is True
                assert "episodes" in r["data"]
