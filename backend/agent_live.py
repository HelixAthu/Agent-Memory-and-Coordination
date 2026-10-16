"""Live agent turn loop coordinating LLM sessions, MCP bridge tools, and event streams."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from backend.crew import AgentTurnResult
from backend.events import EventBus
from backend.llm import make_session
from backend.llm.base import LLMSession, ToolResult
from backend.mcp_bridge import MCPBridge, MemoryContext
from backend.prompts import runtime_block, system_prompt
from memory_core.config import settings
from memory_core.history import append_message


def strip_evidence_graph(envelope: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of the MCP envelope without evidence.graph for the LLM."""
    clean = dict(envelope)
    if "evidence" in clean and isinstance(clean["evidence"], dict):
        clean["evidence"] = {k: v for k, v in clean["evidence"].items() if k != "graph"}
    return clean


async def run_agent_turn(
    ctx: MemoryContext,
    role: str,
    agent_name: str,
    input_text: str,
    bus: EventBus,
    session: LLMSession | None = None,
    bridge: MCPBridge | None = None,
) -> AgentTurnResult:
    """Execute a single agent turn loop against an LLM session and MCP tools.

    Manages call budgets, loop bounds, thought signature propagation,
    specialized event emission from tool envelopes, and persistence.
    """
    mcp_bridge = bridge or MCPBridge()
    tools = await mcp_bridge.tools_for(role)

    llm_session = session or make_session(
        provider=settings.llm_provider,
        system=system_prompt(role, agent_name),
        tools=tools,
    )

    prompt_text = runtime_block(ctx) + input_text
    turn = await llm_session.send_user(prompt_text)

    calls_made: int = 0
    seen_calls: Counter[tuple[str, str]] = Counter()
    handoff_created: str | None = None
    messages_saved: list[dict[str, Any]] = []

    while True:
        if turn.text and turn.text.strip():
            msg = await append_message(
                tenant_id=ctx.tenant_id,
                session_id=ctx.session_id,
                role="agent",
                text=turn.text.strip(),
                agent_id=ctx.agent_id,
            )
            messages_saved.append(msg)
            await bus.emit(
                "message",
                {
                    "role": "agent",
                    "agent_id": ctx.agent_id,
                    "text": turn.text.strip(),
                    "seq": msg["seq"],
                },
            )

        if not turn.tool_calls:
            break

        results: list[ToolResult] = []
        abort_turn: bool = False

        for call in turn.tool_calls:
            calls_made += 1
            if calls_made > 10:
                await bus.emit(
                    "error",
                    {
                        "message": "Call limit exceeded (> 10 calls in turn)",
                        "recoverable": False,
                    },
                )
                abort_turn = True
                break

            call_key = (call.name, json.dumps(call.args, sort_keys=True))
            seen_calls[call_key] += 1
            if seen_calls[call_key] > 2:
                await bus.emit(
                    "error",
                    {
                        "message": f"Repeated tool call aborted: {call.name}",
                        "recoverable": False,
                    },
                )
                abort_turn = True
                break

            await bus.emit(
                "tool_call",
                {
                    "call_id": call.id,
                    "agent_id": ctx.agent_id,
                    "tool": call.name,
                    "args": call.args,
                },
            )

            envelope = await mcp_bridge.call(ctx, call.name, call.args, bus=bus)

            visit = envelope.get("visit", {})
            await bus.emit(
                "memory_visit",
                {
                    "call_id": call.id,
                    "kind": visit.get("kind", "read"),
                    "node_ids": visit.get("node_ids", []),
                    "edge_keys": visit.get("edge_keys", []),
                },
            )

            evidence = envelope.get("evidence", {})
            data = envelope.get("data", {})
            summary = (
                f"{len(data)} items"
                if isinstance(data, (list, dict))
                else str(data)[:30]
            )
            await bus.emit(
                "tool_result",
                {
                    "call_id": call.id,
                    "ok": envelope.get("ok", False),
                    "summary": summary,
                    "query_ids": evidence.get("query_ids", []),
                    "ms": evidence.get("ms", 0.0),
                },
            )

            # Specialised events derived from real tool envelopes
            if call.name == "recall_memory" and envelope.get("ok"):
                d_rec = envelope.get("data", {})
                await bus.emit(
                    "recall_result",
                    {
                        "episodes": [
                            {
                                "id": ep["id"],
                                "score": ep.get("score", 0.0),
                                "components": ep.get("components", {}),
                            }
                            for ep in d_rec.get("episodes", [])
                        ],
                        "fact_ids": [f["id"] for f in d_rec.get("facts", [])],
                        "procedure_ids": [p["id"] for p in d_rec.get("procedures", [])],
                    },
                )
            elif call.name == "remember_fact" and envelope.get("ok"):
                fd = envelope.get("data", {})
                await bus.emit(
                    "fact_update",
                    {
                        "action": fd.get("action", "superseded"),
                        "fact_id": fd.get("fact_id"),
                        "old_fact_id": fd.get("old_fact_id"),
                        "predicate": fd.get("predicate", call.args.get("predicate")),
                        "object": fd.get("object", call.args.get("object")),
                    },
                )
            elif call.name == "create_handoff" and envelope.get("ok"):
                hd = envelope.get("data", {})
                handoff_created = hd.get("handoff_id")
                await bus.emit(
                    "handoff",
                    {
                        "handoff_id": handoff_created,
                        "status": "PENDING",
                        "from_agent": ctx.agent_id,
                        "to_agent": call.args.get("to_agent_id"),
                        "carries": hd.get("carries", {}),
                    },
                )
            elif call.name == "accept_handoff" and envelope.get("ok"):
                hd = envelope.get("data", {})
                await bus.emit(
                    "handoff",
                    {
                        "handoff_id": call.args.get("handoff_id"),
                        "status": "ACCEPTED",
                        "from_agent": hd.get("from_agent", "agent-triage"),
                        "to_agent": ctx.agent_id,
                        "carries": hd.get("carries", {}),
                    },
                )
            elif call.name == "complete_handoff" and envelope.get("ok"):
                hd = envelope.get("data", {})
                await bus.emit(
                    "handoff",
                    {
                        "handoff_id": call.args.get("handoff_id"),
                        "status": "COMPLETED",
                        "from_agent": hd.get("from_agent", "agent-triage"),
                        "to_agent": ctx.agent_id,
                        "carries": hd.get("carries", {}),
                    },
                )
            elif call.name == "record_procedure_outcome" and envelope.get("ok"):
                await bus.emit(
                    "procedure_event",
                    {
                        "procedure_id": call.args.get("procedure_id"),
                        "kind": "outcome",
                        "detail": call.args.get("outcome"),
                    },
                )
            elif call.name == "close_session" and envelope.get("ok"):
                cd = envelope.get("data", {})
                promoted = cd.get("promoted", [])
                for p_id in promoted:
                    await bus.emit(
                        "procedure_event",
                        {
                            "procedure_id": p_id,
                            "kind": "promoted",
                            "detail": "promoted to ACTIVE",
                        },
                    )
                await bus.emit(
                    "session_closed",
                    {
                        "episode_id": cd.get("episode_id"),
                        "importance": cd.get("importance"),
                        "facts_changed": cd.get("facts_changed", []),
                        "promoted": promoted,
                    },
                )
            elif (
                call.name in ("create_task", "claim_task", "claim_next_task", "complete_task")
                and envelope.get("ok")
            ):
                td = envelope.get("data", {})
                await bus.emit(
                    "task_event",
                    {
                        "task_id": td.get("id", call.args.get("task_id")),
                        "status": td.get("status", "UPDATED"),
                        "agent_id": ctx.agent_id,
                    },
                )

            tool_content = strip_evidence_graph(envelope)
            is_err = not envelope.get("ok", False)
            results.append(
                ToolResult(
                    call_id=call.id,
                    name=call.name,
                    content=tool_content,
                    is_error=is_err,
                )
            )

        if abort_turn:
            break

        turn = await llm_session.send_tool_results(results)

    return AgentTurnResult(
        messages=messages_saved,
        handoff_created=handoff_created,
    )
