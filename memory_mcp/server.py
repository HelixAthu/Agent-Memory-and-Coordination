"""Memory Fabric Model Context Protocol (MCP) server implementation.

Exposes memory and coordination tools over stdio/SSE using the Model Context Protocol.
"""

from __future__ import annotations

import time
from typing import Any

from mcp.server.mcpserver import MCPServer

from memory_core.errors import ConflictError, MemoryError
from memory_mcp.context import validate_context
from memory_mcp.envelope import make_envelope, make_error_envelope, serialize_envelope

__all__ = [
    "handle_exception",
    "make_success_envelope",
    "mcp",
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


if __name__ == "__main__":
    mcp.run(transport="stdio")
