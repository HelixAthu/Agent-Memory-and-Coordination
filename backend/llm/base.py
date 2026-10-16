"""Provider-neutral LLM abstraction layer for tool calling and conversation turns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolSpec:
    """Specification of an LLM-callable tool."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class ToolCall:
    """A tool invocation issued by the LLM."""

    id: str
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Execution result of a tool call delivered back to the LLM."""

    call_id: str
    name: str
    content: dict[str, Any]
    is_error: bool = False


@dataclass
class LLMTurn:
    """A single turn response from the LLM containing generated text and tool calls."""

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMSession(Protocol):
    """Protocol implemented by LLM provider session adapters."""

    async def send_user(self, text: str) -> LLMTurn:
        """Send a user message turn and obtain LLM response."""
        ...

    async def send_tool_results(self, results: list[ToolResult]) -> LLMTurn:
        """Send execution results for previously requested tool calls and obtain next LLM turn."""
        ...
