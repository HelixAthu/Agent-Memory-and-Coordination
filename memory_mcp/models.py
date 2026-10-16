"""Pydantic input models for the 16 MCP memory and coordination tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MCPBaseModel(BaseModel):
    """Base Pydantic model prohibiting unions and extra attributes."""

    model_config = ConfigDict(extra="ignore")


class GetUserProfileInput(MCPBaseModel):
    """Input parameters for get_user_profile."""

    include_history: bool = Field(
        default=False,
        description="Whether to return historical superseded facts alongside active facts",
    )


class RecallMemoryInput(MCPBaseModel):
    """Input parameters for recall_memory."""

    query: str = Field(description="Search text to recall relevant episodes, facts, and procedures")
    k: int = Field(default=3, ge=1, le=5, description="Number of top episodes to retrieve")


class RememberFactInput(MCPBaseModel):
    """Input parameters for remember_fact."""

    predicate: Literal["plan", "prefers_channel", "city"] = Field(
        description="Predicate key for the fact"
    )
    object: str = Field(description="Entity or attribute value for the predicate")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence score")


class FindProcedureInput(MCPBaseModel):
    """Input parameters for find_procedure."""

    situation: str = Field(description="Operational context or trigger situation")
    include_candidates: bool = Field(
        default=True,
        description="Whether to include CANDIDATE procedures alongside ACTIVE ones",
    )


class RecordProcedureOutcomeInput(MCPBaseModel):
    """Input parameters for record_procedure_outcome."""

    procedure_id: str = Field(description="Identifier of the executed procedure")
    outcome: Literal["success", "failure"] = Field(description="Outcome of procedure execution")


class RouteToSpecialistInput(MCPBaseModel):
    """Input parameters for route_to_specialist."""

    topic_id: str = Field(description="Topic identifier to find expert specialist agents for")


class CreateHandoffInput(MCPBaseModel):
    """Input parameters for create_handoff."""

    to_agent_id: str = Field(description="Identifier of target specialist agent to receive handoff")
    reason: str = Field(description="Operational rationale for initiating the handoff")


class GetPendingHandoffsInput(MCPBaseModel):
    """Input parameters for get_pending_handoffs."""


class AcceptHandoffInput(MCPBaseModel):
    """Input parameters for accept_handoff."""

    handoff_id: str = Field(description="Identifier of the pending handoff to accept")


class CompleteHandoffInput(MCPBaseModel):
    """Input parameters for complete_handoff."""

    handoff_id: str = Field(description="Identifier of the accepted handoff to complete")
    outcome: Literal["resolved", "escalated"] = Field(description="Resolution outcome")
    summary: str = Field(description="Summary of actions taken during the handoff session")


class CreateTaskInput(MCPBaseModel):
    """Input parameters for create_task."""

    title: str = Field(description="Task description and title")
    priority: int = Field(default=1, ge=1, le=5, description="Task priority (1 to 5)")


class ClaimNextTaskInput(MCPBaseModel):
    """Input parameters for claim_next_task."""


class CompleteTaskInput(MCPBaseModel):
    """Input parameters for complete_task."""

    task_id: str = Field(description="Identifier of the claimed task to mark DONE")


class GetSharedStateInput(MCPBaseModel):
    """Input parameters for get_shared_state."""

    key: str = Field(description="State key matching ^[a-z][a-z0-9_]{0,31}$")


class SetSharedStateInput(MCPBaseModel):
    """Input parameters for set_shared_state."""

    key: str = Field(description="State key matching ^[a-z][a-z0-9_]{0,31}$")
    value: str = Field(description="Value string up to 2000 characters")
    expected_version: int = Field(
        default=0,
        description="Expected version for CAS optimistic concurrency (0 to create)",
    )


class CloseSessionInput(MCPBaseModel):
    """Input parameters for close_session."""

    outcome: Literal["resolved", "escalated", "abandoned"] = Field(
        description="Final session outcome"
    )
    summary: str = Field(default="", description="Optional summary of session resolution")
