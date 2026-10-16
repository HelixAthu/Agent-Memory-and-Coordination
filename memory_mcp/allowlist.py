"""Role allowlists specifying permitted MCP memory and coordination tools per agent role."""

from __future__ import annotations

TRIAGE_TOOLS: set[str] = {
    "get_user_profile",
    "recall_memory",
    "remember_fact",
    "find_procedure",
    "route_to_specialist",
    "create_handoff",
    "create_task",
    "close_session",
}

SPECIALIST_TOOLS: set[str] = {
    "get_user_profile",
    "recall_memory",
    "remember_fact",
    "find_procedure",
    "record_procedure_outcome",
    "get_pending_handoffs",
    "accept_handoff",
    "complete_handoff",
    "claim_next_task",
    "complete_task",
    "get_shared_state",
    "set_shared_state",
    "close_session",
}

ROLE_ALLOWLISTS: dict[str, set[str]] = {
    "triage": TRIAGE_TOOLS,
    "specialist": SPECIALIST_TOOLS,
}


def is_tool_allowed(role: str, tool_name: str) -> bool:
    """Check if the given tool is permitted for the specified agent role."""
    allowed = ROLE_ALLOWLISTS.get(role, set())
    return tool_name in allowed
