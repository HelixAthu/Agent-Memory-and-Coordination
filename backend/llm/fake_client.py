"""Scripted fake LLM session adapter for deterministic testing."""

from __future__ import annotations

from typing import Any

from backend.llm.base import LLMSession, LLMTurn, ToolResult, ToolSpec


class FakeSession(LLMSession):
    """Scripted LLM session simulating turns without calling external APIs."""

    def __init__(
        self,
        system: str = "",
        tools: list[ToolSpec] | None = None,
        scripted_turns: list[LLMTurn] | None = None,
    ) -> None:
        self.system: str = system
        self.tools: list[ToolSpec] = tools or []
        self.scripted_turns: list[LLMTurn] = list(scripted_turns or [])
        self.received_prompts: list[str] = []
        self.received_results: list[list[ToolResult]] = []
        self.history: list[dict[str, Any]] = []

    async def send_user(self, text: str) -> LLMTurn:
        """Record user prompt and return next scripted turn."""
        self.received_prompts.append(text)
        self.history.append({"role": "user", "text": text})
        if self.scripted_turns:
            turn = self.scripted_turns.pop(0)
            self.history.append({"role": "assistant", "turn": turn})
            return turn
        return LLMTurn(text="OK", tool_calls=[])

    async def send_tool_results(self, results: list[ToolResult]) -> LLMTurn:
        """Record tool results and return next scripted turn."""
        self.received_results.append(results)
        self.history.append({"role": "tool_results", "results": results})
        if self.scripted_turns:
            turn = self.scripted_turns.pop(0)
            self.history.append({"role": "assistant", "turn": turn})
            return turn
        return LLMTurn(text="Task completed", tool_calls=[])
