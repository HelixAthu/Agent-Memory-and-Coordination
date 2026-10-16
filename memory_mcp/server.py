"""Memory Fabric Model Context Protocol (MCP) server implementation.

Exposes memory and coordination tools over stdio/SSE using the Model Context Protocol.
"""

from __future__ import annotations

import time
from typing import Any

from mcp.server.mcpserver import MCPServer

from memory_core.consolidation import close_session as core_close_session
from memory_core.coordination import (
    accept_handoff as core_accept_handoff,
)
from memory_core.coordination import (
    claim_next,
    get_state,
    pending_handoffs,
    route,
    set_state,
)
from memory_core.coordination import (
    complete_handoff as core_complete_handoff,
)
from memory_core.coordination import (
    complete_task as core_complete_task,
)
from memory_core.coordination import (
    create_handoff as core_create_handoff,
)
from memory_core.coordination import (
    create_task as core_create_task,
)
from memory_core.db import get_tenant_db
from memory_core.errors import ConflictError, MemoryError
from memory_core.procedural import find_procedures, record_outcome
from memory_core.queries import Q_PROC_STATS
from memory_core.recall import recall
from memory_core.semantic import get_history, get_profile
from memory_core.semantic import remember_fact as core_remember_fact
from memory_mcp.context import validate_context
from memory_mcp.envelope import make_envelope, make_error_envelope, serialize_envelope

__all__ = [
    "accept_handoff",
    "claim_next_task",
    "close_session",
    "complete_handoff",
    "complete_task",
    "create_handoff",
    "create_task",
    "find_procedure",
    "get_pending_handoffs",
    "get_shared_state",
    "get_user_profile",
    "handle_exception",
    "make_success_envelope",
    "mcp",
    "recall_memory",
    "record_procedure_outcome",
    "remember_fact",
    "route_to_specialist",
    "set_shared_state",
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
        state_data = await get_state(tenant_id, session_id, key)
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


@mcp.tool(
    description=(
        "Record, update, or supersede a semantic user attribute in memory. "
        "Use when: customer explicitly states an updated plan, preferred contact channel, or city. "
        "Do not use when: logging episodic conversation details or procedures."
    )
)
async def remember_fact(
    tenant_id: str,
    user_id: str,
    agent_id: str,
    session_id: str,
    predicate: str,
    object: str,
    confidence: float = 0.8,
) -> str:
    start_time = time.perf_counter()
    try:
        await validate_context(
            tenant_id, user_id, agent_id, session_id, tool_name="remember_fact"
        )
        res = await core_remember_fact(
            tenant_id=tenant_id,
            user_id=user_id,
            predicate=predicate,
            object_=object,
            confidence=confidence,
            session_id=session_id,
        )
        data = {
            "action": res["action"],
            "fact_id": res["fact_id"],
            "old_fact_id": res["old_fact_id"],
        }
        node_ids = [res["fact_id"]]
        if res.get("old_fact_id"):
            node_ids.append(res["old_fact_id"])
        return make_success_envelope(
            data=data,
            visit_kind="write",
            node_ids=node_ids,
            edge_keys=[],
            query_ids=["Q-FACT-CAS-WRITE"],
            tenant_id=tenant_id,
            start_time=start_time,
        )
    except Exception as e:
        return handle_exception(e)


@mcp.tool(
    description=(
        "Record the execution result of an operational procedure for Bayesian learning. "
        "Use when: an agent completes a workflow according to a procedure and observes success or failure. "
        "Do not use when: closing the general session."
    )
)
async def record_procedure_outcome(
    tenant_id: str,
    user_id: str,
    agent_id: str,
    session_id: str,
    procedure_id: str,
    outcome: str,
) -> str:
    start_time = time.perf_counter()
    try:
        await validate_context(
            tenant_id, user_id, agent_id, session_id, tool_name="record_procedure_outcome"
        )
        await record_outcome(
            tenant_id=tenant_id,
            session_id=session_id,
            procedure_id=procedure_id,
            outcome=outcome,
        )
        db = await get_tenant_db(tenant_id)
        stats = await db.run_ro(Q_PROC_STATS, {"pid": procedure_id})
        successes = int(stats[0][1] or 0) if stats else 0
        failures = int(stats[0][2] or 0) if stats else 0
        success_users = int(stats[0][3] or 0) if stats else 0
        data = {
            "procedure_id": procedure_id,
            "outcome": outcome,
            "successes": successes,
            "failures": failures,
            "success_users": success_users,
        }
        return make_success_envelope(
            data=data,
            visit_kind="write",
            node_ids=[procedure_id],
            edge_keys=[],
            query_ids=["Q-PROC-OUTCOME"],
            tenant_id=tenant_id,
            start_time=start_time,
        )
    except Exception as e:
        return handle_exception(e)


@mcp.tool(
    description=(
        "Find qualified specialist agents for a specific support topic ranked by current workload. "
        "Use when: identifying the optimal agent to escalate or transfer a customer to. "
        "Do not use when: initiating the actual transfer."
    )
)
async def route_to_specialist(
    tenant_id: str,
    user_id: str,
    agent_id: str,
    session_id: str,
    topic_id: str,
) -> str:
    start_time = time.perf_counter()
    try:
        await validate_context(
            tenant_id, user_id, agent_id, session_id, tool_name="route_to_specialist"
        )
        candidate_ids = await route(tenant_id=tenant_id, topic_id=topic_id)
        db = await get_tenant_db(tenant_id)
        candidates: list[dict[str, Any]] = []
        for aid in candidate_ids:
            agent_info = await db.run_ro(
                "MATCH (a:Agent {id: $aid}) "
                "OPTIONAL MATCH (t:Task) WHERE t.status = 'CLAIMED' AND t.claimed_by = a.id "
                "RETURN a.id, a.name, count(t)",
                {"aid": aid},
            )
            if agent_info:
                candidates.append(
                    {
                        "id": str(agent_info[0][0]),
                        "name": str(agent_info[0][1]),
                        "load": int(agent_info[0][2]),
                    }
                )
            else:
                candidates.append({"id": aid, "name": aid, "load": 0})
        data = {"candidates": candidates}
        return make_success_envelope(
            data=data,
            visit_kind="read",
            node_ids=[c["id"] for c in candidates],
            edge_keys=[],
            query_ids=["Q-AGENT-ROUTE"],
            tenant_id=tenant_id,
            start_time=start_time,
        )
    except Exception as e:
        return handle_exception(e)


@mcp.tool(
    description=(
        "Initiate an explicit conversational handoff transferring the customer to a specialist. "
        "Use when: transferring customer context, facts, and recent history to another agent. "
        "Do not use when: answering customer inquiries directly without delegation."
    )
)
async def create_handoff(
    tenant_id: str,
    user_id: str,
    agent_id: str,
    session_id: str,
    to_agent_id: str,
    reason: str,
) -> str:
    start_time = time.perf_counter()
    try:
        await validate_context(
            tenant_id, user_id, agent_id, session_id, tool_name="create_handoff"
        )
        res = await core_create_handoff(
            tenant_id=tenant_id,
            session_id=session_id,
            from_agent=agent_id,
            to_agent=to_agent_id,
            reason=reason,
        )
        return make_success_envelope(
            data=res,
            visit_kind="handoff",
            node_ids=[res["handoff_id"]],
            edge_keys=[],
            query_ids=["Q-HANDOFF-CREATE"],
            tenant_id=tenant_id,
            start_time=start_time,
        )
    except Exception as e:
        return handle_exception(e)


@mcp.tool(
    description=(
        "Accept a pending handoff and unpack the bundled memory context and history. "
        "Use when: an agent receives a transfer and takes ownership of the customer conversation. "
        "Do not use when: creating a new transfer."
    )
)
async def accept_handoff(
    tenant_id: str,
    user_id: str,
    agent_id: str,
    session_id: str,
    handoff_id: str,
) -> str:
    start_time = time.perf_counter()
    try:
        await validate_context(
            tenant_id, user_id, agent_id, session_id, tool_name="accept_handoff"
        )
        res = await core_accept_handoff(
            tenant_id=tenant_id,
            handoff_id=handoff_id,
            agent_id=agent_id,
        )
        data = {
            "handoff_id": res["handoff_id"],
            "status": "ACCEPTED",
            "bundle": res["bundle"],
        }
        return make_success_envelope(
            data=data,
            visit_kind="handoff",
            node_ids=[res["handoff_id"]],
            edge_keys=[],
            query_ids=["Q-HANDOFF-ACCEPT"],
            tenant_id=tenant_id,
            start_time=start_time,
        )
    except Exception as e:
        return handle_exception(e)


@mcp.tool(
    description=(
        "Conclude an accepted handoff with resolution status and summary. "
        "Use when: finishing work on a transferred task or escalating it further. "
        "Do not use when: initially accepting the handoff."
    )
)
async def complete_handoff(
    tenant_id: str,
    user_id: str,
    agent_id: str,
    session_id: str,
    handoff_id: str,
    outcome: str,
    summary: str,
) -> str:
    start_time = time.perf_counter()
    try:
        await validate_context(
            tenant_id, user_id, agent_id, session_id, tool_name="complete_handoff"
        )
        await core_complete_handoff(
            tenant_id=tenant_id,
            handoff_id=handoff_id,
            agent_id=agent_id,
            outcome=outcome,
            summary=summary,
        )
        return make_success_envelope(
            data={"handoff_id": handoff_id, "status": "COMPLETED"},
            visit_kind="handoff",
            node_ids=[handoff_id],
            edge_keys=[],
            query_ids=["Q-HANDOFF-COMPLETE"],
            tenant_id=tenant_id,
            start_time=start_time,
        )
    except Exception as e:
        return handle_exception(e)


@mcp.tool(
    description=(
        "Create a new coordination task linked to the customer for agent processing. "
        "Use when: queueing work items that can be claimed and processed asynchronously. "
        "Do not use when: updating shared state variables."
    )
)
async def create_task(
    tenant_id: str,
    user_id: str,
    agent_id: str,
    session_id: str,
    title: str,
    priority: int = 1,
) -> str:
    start_time = time.perf_counter()
    try:
        await validate_context(
            tenant_id, user_id, agent_id, session_id, tool_name="create_task"
        )
        task_id = await core_create_task(
            tenant_id=tenant_id,
            user_id=user_id,
            title=title,
            priority=priority,
        )
        return make_success_envelope(
            data={"task_id": task_id},
            visit_kind="task",
            node_ids=[task_id],
            edge_keys=[],
            query_ids=["Q-TASK-CREATE"],
            tenant_id=tenant_id,
            start_time=start_time,
        )
    except Exception as e:
        return handle_exception(e)


@mcp.tool(
    description=(
        "Atomically claim the highest priority unassigned coordination task. "
        "Use when: an agent is ready to pull work from the operational task backlog. "
        "Do not use when: looking up customer profile or procedures."
    )
)
async def claim_next_task(
    tenant_id: str,
    user_id: str,
    agent_id: str,
    session_id: str,
) -> str:
    start_time = time.perf_counter()
    try:
        await validate_context(
            tenant_id, user_id, agent_id, session_id, tool_name="claim_next_task"
        )
        claimed = await claim_next(tenant_id=tenant_id, agent_id=agent_id)
        if claimed:
            data = {
                "task_id": claimed["id"],
                "title": claimed["title"],
                "version": claimed["version"],
            }
            node_ids = [claimed["id"]]
        else:
            data = {"task_id": None, "title": "", "version": 0}
            node_ids = []
        return make_success_envelope(
            data=data,
            visit_kind="task",
            node_ids=node_ids,
            edge_keys=[],
            query_ids=["Q-TASK-CLAIM"],
            tenant_id=tenant_id,
            start_time=start_time,
        )
    except Exception as e:
        return handle_exception(e)


@mcp.tool(
    description=(
        "Mark a claimed coordination task as completed. "
        "Use when: finished executing work associated with a claimed task. "
        "Do not use when: completing a conversational handoff."
    )
)
async def complete_task(
    tenant_id: str,
    user_id: str,
    agent_id: str,
    session_id: str,
    task_id: str,
) -> str:
    start_time = time.perf_counter()
    try:
        await validate_context(
            tenant_id, user_id, agent_id, session_id, tool_name="complete_task"
        )
        await core_complete_task(
            tenant_id=tenant_id,
            task_id=task_id,
            agent_id=agent_id,
        )
        return make_success_envelope(
            data={"task_id": task_id, "status": "DONE"},
            visit_kind="task",
            node_ids=[task_id],
            edge_keys=[],
            query_ids=["Q-TASK-COMPLETE"],
            tenant_id=tenant_id,
            start_time=start_time,
        )
    except Exception as e:
        return handle_exception(e)


@mcp.tool(
    description=(
        "Update a shared multi-agent state variable using compare-and-swap (CAS). "
        "Use when: synchronizing coordinated values across multiple collaborating agents. "
        "Do not use when: storing user-specific facts."
    )
)
async def set_shared_state(
    tenant_id: str,
    user_id: str,
    agent_id: str,
    session_id: str,
    key: str,
    value: str,
    expected_version: int = 0,
) -> str:
    start_time = time.perf_counter()
    try:
        await validate_context(
            tenant_id, user_id, agent_id, session_id, tool_name="set_shared_state"
        )
        new_version = await set_state(
            tenant_id=tenant_id,
            session_id=session_id,
            key=key,
            value=value,
            expected_version=expected_version,
            agent_id=agent_id,
        )
        return make_success_envelope(
            data={"key": key, "version": new_version},
            visit_kind="state",
            node_ids=[f"state-{key}"],
            edge_keys=[],
            query_ids=["Q-STATE-SET"],
            tenant_id=tenant_id,
            start_time=start_time,
        )
    except Exception as e:
        return handle_exception(e)


@mcp.tool(
    description=(
        "Close current session, triggering episodic consolidation and procedural promotion. "
        "Use when: customer interaction has concluded and memories should be consolidated. "
        "Do not use when: in the middle of active turns."
    )
)
async def close_session(
    tenant_id: str,
    user_id: str,
    agent_id: str,
    session_id: str,
    outcome: str,
    summary: str = "",
) -> str:
    start_time = time.perf_counter()
    try:
        await validate_context(
            tenant_id, user_id, agent_id, session_id, tool_name="close_session"
        )
        res = await core_close_session(
            tenant_id=tenant_id,
            session_id=session_id,
            outcome=outcome,
            summary=summary,
        )
        node_ids = []
        if res.get("episode_id"):
            node_ids.append(res["episode_id"])
        node_ids.extend(res.get("promoted", []))
        return make_success_envelope(
            data=res,
            visit_kind="write",
            node_ids=node_ids,
            edge_keys=[],
            query_ids=["Q-SESSION-CLOSE", "Q-EP-CREATE"],
            tenant_id=tenant_id,
            start_time=start_time,
        )
    except Exception as e:
        return handle_exception(e)


if __name__ == "__main__":
    mcp.run(transport="stdio")
