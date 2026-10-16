"""Gemini LLM session adapter handling tool schemas, thinking config, and thought signatures."""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

from google import genai
from google.genai import errors, types

from backend.llm.base import LLMError, LLMSession, LLMTurn, ToolCall, ToolResult, ToolSpec
from memory_core.config import settings

VALID_THINKING_LEVELS: set[str] = {"low", "medium", "high"}


class GeminiSession(LLMSession):
    """Gemini session adapter maintaining conversation history and thought signatures."""

    def __init__(
        self,
        system: str,
        tools: list[ToolSpec],
        api_key: str | None = None,
        model: str | None = None,
        thinking_level: str | None = None,
        client: Any | None = None,
    ) -> None:
        lvl = thinking_level or settings.gemini_thinking_level or "medium"
        if lvl not in VALID_THINKING_LEVELS:
            raise ValueError(
                f"Thinking level '{lvl}' is not supported. Must be one of: {sorted(VALID_THINKING_LEVELS)}"
            )

        self.thinking_level: str = lvl
        self.model: str = model or settings.gemini_model or "gemini-3.8-flash"
        self.api_key: str = api_key or os.getenv("GEMINI_API_KEY", "") or settings.gemini_api_key

        if client is not None:
            self.client = client
        else:
            self.client = genai.Client(api_key=self.api_key)

        decls: list[types.FunctionDeclaration] = [
            types.FunctionDeclaration(
                name=t.name,
                description=t.description,
                parameters_json_schema=t.input_schema,
            )
            for t in tools
        ]

        self.config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(function_declarations=decls)],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            thinking_config=types.ThinkingConfig(thinking_level=self.thinking_level),
        )

        self.contents: list[types.Content] = []

    async def send_user(self, text: str) -> LLMTurn:
        """Append user message to history and generate response."""
        self.contents.append(types.Content(role="user", parts=[types.Part.from_text(text=text)]))
        return await self._generate()

    async def send_tool_results(self, results: list[ToolResult]) -> LLMTurn:
        """Send all tool results in a single turn matching previous tool call order."""
        parts: list[types.Part] = [
            types.Part.from_function_response(
                name=r.name,
                response={"error": r.content} if r.is_error else {"output": r.content},
            )
            for r in results
        ]
        self.contents.append(types.Content(role="user", parts=parts))
        return await self._generate()

    async def _generate(self) -> LLMTurn:
        """Generate content from model with exponential backoff on retryable status codes."""
        backoffs: list[float] = [1.0, 2.0, 4.0]

        for attempt, delay in enumerate(backoffs):
            try:
                resp = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=self.model,
                        contents=self.contents,
                        config=self.config,
                    ),
                    timeout=60.0,
                )

                if not resp.candidates or not resp.candidates[0].content:
                    raise LLMError("Gemini returned empty candidate content")

                content = resp.candidates[0].content
                # VERBATIM append to history to preserve thought signatures
                self.contents.append(content)

                text = "".join(
                    p.text
                    for p in (content.parts or [])
                    if getattr(p, "text", None) and not getattr(p, "thought", False)
                )

                calls = [
                    ToolCall(
                        id=uuid.uuid4().hex[:8],
                        name=p.function_call.name,
                        args=dict(p.function_call.args or {}),
                    )
                    for p in (content.parts or [])
                    if getattr(p, "function_call", None)
                ]

                return LLMTurn(text=text, tool_calls=calls)

            except errors.APIError as e:
                code = getattr(e, "code", None)
                if code == 400:
                    raise LLMError(f"Gemini API 400 error: {e.message}") from e
                if code == 429 or (code is not None and code >= 500):
                    if attempt < len(backoffs) - 1:
                        await asyncio.sleep(delay)
                        continue
                raise LLMError(f"Gemini API error (code {code}): {e.message}") from e
            except asyncio.TimeoutError as e:
                if attempt < len(backoffs) - 1:
                    await asyncio.sleep(delay)
                    continue
                raise LLMError("Gemini call timed out after 60s") from e

        raise LLMError("Gemini call failed after retry attempts")
