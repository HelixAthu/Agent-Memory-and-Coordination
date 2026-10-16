"""Structured response envelope formatting success and error results for MCP tools."""

from __future__ import annotations

import json
from typing import Any


def make_envelope(
    ok: bool,
    data: dict[str, Any] | None = None,
    visit: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standard response envelope."""
    if ok:
        res: dict[str, Any] = {
            "ok": True,
            "data": data or {},
            "visit": visit or {"kind": "read", "node_ids": [], "edge_keys": []},
            "evidence": evidence or {"query_ids": [], "graph": "", "ms": 0.0},
        }
        return res

    return {
        "ok": False,
        "error": error
        or {
            "code": "DB_ERROR",
            "message": "An unspecified error occurred",
            "details": {},
        },
    }


def make_error_envelope(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Helper to construct an error envelope."""
    return make_envelope(
        ok=False,
        error={
            "code": code,
            "message": message,
            "details": details or {},
        },
    )


def serialize_envelope(env: dict[str, Any]) -> str:
    """Serialize envelope to JSON string for MCP text content delivery."""
    return json.dumps(env, ensure_ascii=False)
