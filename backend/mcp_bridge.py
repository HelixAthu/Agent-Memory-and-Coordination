"""MCP Bridge managing context injection, role tool filtering, and envelope handling."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any

from backend.events import EventBus
from backend.llm.base import ToolSpec
from backend.llm.schema import simplify_schema
from memory_mcp.allowlist import is_tool_allowed
from memory_mcp.server import mcp

CONTEXT_FIELDS: set[str] = {"tenant_id", "user_id", "agent_id", "session_id"}


@dataclass
class MemoryContext:
    """Execution context bound to an agent turn."""

    tenant_id: str
    user_id: str
    agent_id: str
    session_id: str

    def with_agent(self, new_agent_id: str) -> MemoryContext:
        """Return a copy of the context with a different acting agent."""
        return MemoryContext(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            agent_id=new_agent_id,
            session_id=self.session_id,
        )


def strip_evidence_graph(envelope: dict[str, Any]) -> dict[str, Any]:
    """Remove evidence.graph before passing tool results to the LLM."""
    clean = copy.deepcopy(envelope)
    if "evidence" in clean and isinstance(clean["evidence"], dict):
        clean["evidence"].pop("graph", None)
    return clean


class MCPBridge:
    """Bridge orchestrating tool schema adaptation, context injection, and MCP calls."""

    def __init__(self) -> None:
        self.mcp = mcp

    async def tools_for(self, role: str) -> list[ToolSpec]:
        """Return adapted and simplified tool specifications permitted for the given role."""
        raw_tools = await self.mcp.list_tools()
        specs: list[ToolSpec] = []

        for t in raw_tools:
            if not is_tool_allowed(role, t.name):
                continue

            schema = copy.deepcopy(t.input_schema)
            if "properties" in schema and isinstance(schema["properties"], dict):
                schema["properties"] = {
                    k: v for k, v in schema["properties"].items() if k not in CONTEXT_FIELDS
                }
            if "required" in schema and isinstance(schema["required"], list):
                schema["required"] = [k for k in schema["required"] if k not in CONTEXT_FIELDS]

            simplified = simplify_schema(schema)
            specs.append(
                ToolSpec(
                    name=t.name,
                    description=t.description or "",
                    input_schema=simplified,
                )
            )

        return specs

    async def call(
        self,
        ctx: MemoryContext,
        tool_name: str,
        args: dict[str, Any],
        bus: EventBus | None = None,
    ) -> dict[str, Any]:
        """Execute MCP tool after stripping caller context and injecting bound context fields."""
        call_args: dict[str, Any] = {}
        for k, v in args.items():
            if k in CONTEXT_FIELDS:
                if bus is not None:
                    await bus.emit(
                        "warning",
                        {
                            "message": (
                                f"Dropped context argument '{k}' from tool call '{tool_name}'"
                            )
                        },
                    )
            else:
                call_args[k] = v

        # Inject bound context parameters
        call_args["tenant_id"] = ctx.tenant_id
        call_args["user_id"] = ctx.user_id
        call_args["agent_id"] = ctx.agent_id
        call_args["session_id"] = ctx.session_id

        res = await self.mcp.call_tool(tool_name, call_args)
        raw_text = res.content[0].text
        envelope: dict[str, Any] = json.loads(raw_text)
        return envelope
