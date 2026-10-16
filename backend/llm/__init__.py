"""LLM provider session factory and neutral interface."""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.llm.base import LLMError, LLMSession, LLMTurn, ToolCall, ToolResult, ToolSpec

if TYPE_CHECKING:
    pass

__all__ = [
    "LLMError",
    "LLMSession",
    "LLMTurn",
    "ToolCall",
    "ToolResult",
    "ToolSpec",
    "make_session",
]


def make_session(
    provider: str,
    system: str,
    tools: list[ToolSpec],
    api_key: str | None = None,
    model: str | None = None,
    thinking_level: str | None = None,
) -> LLMSession:
    """Instantiate a provider-specific LLMSession."""
    prov = provider.lower().strip()
    if prov == "gemini":
        from backend.llm.gemini_client import GeminiSession

        return GeminiSession(
            system=system,
            tools=tools,
            api_key=api_key,
            model=model,
            thinking_level=thinking_level,
        )
    if prov in ("fake", "mock", "test"):
        from backend.llm.fake_client import FakeSession

        return FakeSession(system=system, tools=tools)

    raise ValueError(f"Unsupported LLM provider: '{provider}'")
