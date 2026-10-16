"""Memory Fabric Model Context Protocol (MCP) server implementation.

Exposes memory and coordination tools over stdio/SSE using the Model Context Protocol.
"""

from __future__ import annotations

import time
from typing import Any

from mcp.server.mcpserver import MCPServer

from memory_core.coordination import get_state, pending_handoffs
from memory_core.errors import ConflictError, MemoryError
from memory_core.procedural import find_procedures
from memory_core.recall import recall
from memory_core.semantic import get_history, get_profile
from memory_mcp.context import validate_context
from memory_mcp.envelope import make_envelope, make_error_envelope, serialize_envelope

__all__ = [
    "find_procedure",
    "get_pending_handoffs",
    "get_shared_state",
    "get_user_profile",
    "handle_exception",
    "make_success_envelope",
    "mcp",
    "recall_memory",
    "validate_context",
]

mcp = MCPServer("memory-fabric")


def handle_exception(e: Exception) -> str:
    """Format exceptions into standardized MCP error envelopes."""
    if isinstance(e, ConflictError):
        details: dict[str, Any] = {}
        if e.current_version is not None:
            details["current_version"] = e.current_version
        return serialize_envelope(make_error_envelope(e.code, e.message, details))
    if isinstance(e, MemoryError):
        return serialize_envelope(make_error_envelope(e.code, e.message))
    return serialize_envelope(make_error_envelope("DB_ERROR", str(e)))


def make_success_envelope(
    data: dict[str, Any],
    visit_kind: str,
    node_ids: list[str],
    edge_keys: list[str],
    query_ids: list[str],
    tenant_id: str,
    start_time: float,
) -> str:
    """Build serialized success envelope with telemetry and visit graph."""
    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
    env = make_envelope(
        ok=True,
        data=data,
        visit={"kind": visit_kind, "node_ids": node_ids, "edge_keys": edge_keys},
        evidence={"query_ids": query_ids, "graph": f"mem_{tenant_id}", "ms": elapsed_ms},
    )
    return serialize_envelope(env)


@mcp.tool(
    description=(
        "Retrieve the semantic profile and facts for a user. "
        "Use when: needing active customer facts such as plan, preferred channel, or location. "
        "Do not use when: searching episodic session history or procedural workflows."
    )
)
async def get_user_profile(
    tenant_id: str,
    user_id: str,
    agent_id: str,
    session_id: str,
    include_history: bool = False,
) -> str:
    start_time = time.perf_counter()
    try:
        await validate_context(
            tenant_id, user_id, agent_id, session_id, tool_name="get_user_profile"
        )
        facts = await get_profile(tenant_id, user_id)
        data: dict[str, Any] = {"facts": facts}
        query_ids = ["Q-FACTS-ACTIVE"]
        node_ids = [f["id"] for f in facts]
        if include_history:
            history_data: dict[str, list[dict[str, Any]]] = {}
            for pred in ("plan", "prefers_channel", "city"):
                h_facts = await get_history(tenant_id, user_id, pred)
                history_data[pred] = h_facts
                node_ids.extend([hf["id"] for hf in h_facts])
            data["history"] = history_data
            query_ids.append("Q-FACT-HISTORY")
        return make_success_envelope(
            data=data,
            visit_kind="read",
            node_ids=list(dict.fromkeys(node_ids)),
            edge_keys=[],
            query_ids=query_ids,
            tenant_id=tenant_id,
            start_time=start_time,
        )
    except Exception as e:
        return handle_exception(e)


@mcp.tool(
    description=(
        "Search episodic, semantic, and procedural memory using hybrid vector and graph scoring. "
        "Use when: customer mentions past issues, context, or previous interactions. "
        "Do not use when: looking up a known user attribute directly."
    )
)
async def recall_memory(
    tenant_id: str,
    user_id: str,
    agent_id: str,
    session_id: str,
    query: str,
    k: int = 3,
) -> str:
    start_time = time.perf_counter()
    try:
        await validate_context(
            tenant_id, user_id, agent_id, session_id, tool_name="recall_memory"
        )
        res = await recall(tenant_id, user_id, query, k=k)
        data = {
            "episodes": res["episodes"],
            "facts": res["facts"],
            "procedures": res["procedures"],
        }
        return make_success_envelope(
            data=data,
            visit_kind="recall",
            node_ids=res["visit"]["node_ids"],
            edge_keys=res["visit"]["edge_keys"],
            query_ids=["Q-EP-VEC", "Q-FACTS-ACTIVE", "Q-PROC-VEC"],
            tenant_id=tenant_id,
            start_time=start_time,
        )
    except Exception as e:
        return handle_exception(e)


@mcp.tool(
    description=(
        "Retrieve operational procedure guidelines matching a given operational situation. "
        "Use when: deciding what standard operating procedure or steps to follow for an issue. "
        "Do not use when: recalling past conversational episodes."
    )
)
async def find_procedure(
    tenant_id: str,
    user_id: str,
    agent_id: str,
    session_id: str,
    situation: str,
    include_candidates: bool = True,
) -> str:
    start_time = time.perf_counter()
    try:
        await validate_context(
            tenant_id, user_id, agent_id, session_id, tool_name="find_procedure"
        )
        procedures = await find_procedures(
            tenant_id, situation, include_candidates=include_candidates
        )
        data = {"procedures": procedures}
        return make_success_envelope(
            data=data,
            visit_kind="read",
            node_ids=[p["id"] for p in procedures],
            edge_keys=[],
            query_ids=["Q-PROC-VEC", "Q-PROC-STATS"],
            tenant_id=tenant_id,
            start_time=start_time,
        )
    except Exception as e:
        return handle_exception(e)


@mcp.tool(
    description=(
        "Retrieve incoming pending customer handoffs assigned to the current agent. "
        "Use when: an agent begins a turn to check for transferred conversations. "
        "Do not use when: looking up user history or searching procedures."
    )
)
async def get_pending_handoffs(
    tenant_id: str,
    user_id: str,
    agent_id: str,
    session_id: str,
) -> str:
    start_time = time.perf_counter()
    try:
        await validate_context(
            tenant_id, user_id, agent_id, session_id, tool_name="get_pending_handoffs"
        )
        handoffs = await pending_handoffs(tenant_id, agent_id)
        data = {"handoffs": handoffs}
        return make_success_envelope(
            data=data,
            visit_kind="read",
            node_ids=[h["id"] for h in handoffs],
            edge_keys=[],
            query_ids=["Q-HANDOFF-PENDING"],
            tenant_id=tenant_id,
            start_time=start_time,
        )
    except Exception as e:
        return handle_exception(e)


@mcp.tool(
    description=(
        "Read the value and current version of a shared multi-agent state key. "
        "Use when: checking collaborative coordination state between agents. "
        "Do not use when: reading customer semantic memory or profile."
    )
)
async def get_shared_state(
    tenant_id: str,
    user_id: str,
    agent_id: str,
    session_id: str,
    key: str,
) -> str:
    start_time = time.perf_counter()
    try:
        await validate_context(
            tenant_id, user_id, agent_id, session_id, tool_name="get_shared_state"
        )
        state_data = await get_state(tenant_id, key)
        return make_success_envelope(
            data=state_data,
            visit_kind="state",
            node_ids=[f"state-{key}"],
            edge_keys=[],
            query_ids=["Q-STATE-GET"],
            tenant_id=tenant_id,
            start_time=start_time,
        )
    except Exception as e:
        return handle_exception(e)


if __name__ == "__main__":
    mcp.run(transport="stdio")
