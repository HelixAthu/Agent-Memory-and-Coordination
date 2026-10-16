"""Scenario definitions and metadata for deterministic multi-agent customer workflows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    """Specification of an evaluation scenario."""

    id: str
    tenant_id: str
    user_id: str
    session_id: str
    user_text: str


SCENARIOS: dict[str, Scenario] = {
    "continuity": Scenario(
        id="continuity",
        tenant_id="acme",
        user_id="user-priya",
        session_id="sess-demo-continuity",
        user_text="Hello, my card shows a duplicate charge again on invoice INV-1042.",
    ),
    "fact_update": Scenario(
        id="fact_update",
        tenant_id="acme",
        user_id="user-priya",
        session_id="sess-demo-move",
        user_text="By the way, I moved to Pune and I prefer chat now.",
    ),
    "procedure_learning": Scenario(
        id="procedure_learning",
        tenant_id="acme",
        user_id="user-rahul",
        session_id="sess-demo-vpn",
        user_text="My VPN token expired again.",
    ),
}
