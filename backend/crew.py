"""Crew runner managing multi-agent turns, persistence, and handoff chaining."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.events import EventBus
from backend.mcp_bridge import MemoryContext
from memory_core.config import settings
from memory_core.db import get_tenant_db
from memory_core.history import append_message


@dataclass
class AgentTurnResult:
    """Outcome of an agent turn."""

    messages: list[dict[str, Any]] = field(default_factory=list)
    handoff_created: str | None = None


async def run_agent(
    ctx: MemoryContext,
    user_text: str,
    bus: EventBus,
    mode: str | None = None,
) -> AgentTurnResult:
    """Dispatch agent turn to live Gemini loop or scripted mock runner."""
    active_mode = mode or settings.agent_mode
    if active_mode == "live":
        from backend.agent_live import run_agent_turn

        role = "triage" if "triage" in ctx.agent_id else "specialist"
        return await run_agent_turn(
            ctx=ctx,
            role=role,
            agent_name=ctx.agent_id,
            input_text=user_text,
            bus=bus,
        )

    from backend.agent_mock import MockAgentRunner

    runner = MockAgentRunner()
    return await runner.run_turn(ctx, user_text, bus)


async def run_turn(
    ctx: MemoryContext,
    user_text: str,
    bus: EventBus | None = None,
    mode: str | None = None,
) -> EventBus:
    """Run a multi-agent user turn with automatic handoff chaining up to 2 hops.

    Persists the incoming user turn message, selects the current active agent
    from the session graph node, triggers agent execution, and chains up to
    two handoffs to specialist agents before closing the turn.
    """
    event_bus = bus or EventBus()

    # 1. Append user message and emit message event
    msg = await append_message(
        tenant_id=ctx.tenant_id,
        session_id=ctx.session_id,
        role="user",
        text=user_text,
    )
    await event_bus.emit(
        "message",
        {"role": "user", "agent_id": None, "text": user_text, "seq": msg["seq"]},
    )

    # 2. Read session.current_agent from graph
    db = await get_tenant_db(ctx.tenant_id)
    res = await db.run_ro(
        "MATCH (s:Session {id: $sid}) RETURN s.current_agent",
        {"sid": ctx.session_id},
    )
    agent = str(res[0][0]) if res and res[0][0] else "agent-triage"

    # 3. Emit agent_active
    role = "triage" if "triage" in agent else "specialist"
    await event_bus.emit("agent_active", {"agent_id": agent, "role": role})

    # 4. Run agent turn
    result = await run_agent(ctx.with_agent(agent), user_text, event_bus, mode=mode)

    # 5. Handoff chaining: up to 2 hops
    hops = 0
    while result.handoff_created and hops < 2:
        hops += 1
        ho_res = await db.run_ro(
            "MATCH (h:Handoff {id: $hid}) RETURN h.to_agent",
            {"hid": result.handoff_created},
        )
        if not ho_res or not ho_res[0][0]:
            break
        target = str(ho_res[0][0])
        target_role = "triage" if "triage" in target else "specialist"
        await event_bus.emit("agent_active", {"agent_id": target, "role": target_role})
        result = await run_agent(
            ctx.with_agent(target),
            "A handoff is waiting for you. Start with get_pending_handoffs.",
            event_bus,
            mode=mode,
        )

    await event_bus.emit(
        "final",
        {"session_id": ctx.session_id, "summary": "Turn completed successfully"},
    )
    return event_bus
