"""Unit tests for GeminiSession adapter, thought signatures, error retries, and schema simplifier."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from google.genai import errors, types

from backend.llm.base import LLMError, ToolResult, ToolSpec
from backend.llm.gemini_client import GeminiSession
from backend.llm.schema import assert_simple_schema, simplify_schema


@pytest.fixture
def dummy_tool_spec() -> ToolSpec:
    """Fixture dummy tool specification."""
    return ToolSpec(
        name="dummy_tool",
        description="A dummy test tool. Use when: testing. Do not use when: production.",
        input_schema={"type": "object", "properties": {"arg": {"type": "string"}}},
    )


@pytest.mark.asyncio
async def test_model_content_appended_verbatim_identity(dummy_tool_spec: ToolSpec):
    """Assert that the model's Content response is appended to history unchanged (identity check)."""
    mock_client = MagicMock()
    mock_models = MagicMock()
    mock_client.aio.models = mock_models

    returned_content = types.Content(
        role="model",
        parts=[types.Part.from_text(text="Hello world")],
    )
    mock_response = MagicMock()
    mock_response.candidates = [MagicMock(content=returned_content)]
    mock_models.generate_content = AsyncMock(return_value=mock_response)

    session = GeminiSession(
        system="System prompt",
        tools=[dummy_tool_spec],
        api_key="fake-key",
        client=mock_client,
    )

    turn = await session.send_user("Hi")
    assert turn.text == "Hello world"

    # Identity check: verify that the exact returned_content instance was appended
    assert len(session.contents) == 2
    assert session.contents[0].role == "user"
    assert session.contents[1] is returned_content


@pytest.mark.asyncio
async def test_multiple_function_calls_produce_single_results_content(dummy_tool_spec: ToolSpec):
    """Assert several function calls produce ONE results Content with parts in the same order."""
    mock_client = MagicMock()
    mock_models = MagicMock()
    mock_client.aio.models = mock_models

    mock_response = MagicMock()
    mock_response.candidates = [
        MagicMock(content=types.Content(role="model", parts=[types.Part.from_text(text="Done")]))
    ]
    mock_models.generate_content = AsyncMock(return_value=mock_response)

    session = GeminiSession(
        system="System",
        tools=[dummy_tool_spec],
        api_key="fake-key",
        client=mock_client,
    )

    results = [
        ToolResult(call_id="call-1", name="tool_a", content={"val": 1}),
        ToolResult(call_id="call-2", name="tool_b", content={"val": 2}),
        ToolResult(call_id="call-3", name="tool_c", content={"val": 3}),
    ]

    await session.send_tool_results(results)

    # Exactly 2 entries: the tool results content and the model response
    assert len(session.contents) == 2
    tool_content = session.contents[0]
    assert tool_content.role == "user"
    assert len(tool_content.parts) == 3

    # Check order of function response parts
    assert tool_content.parts[0].function_response.name == "tool_a"
    assert tool_content.parts[1].function_response.name == "tool_b"
    assert tool_content.parts[2].function_response.name == "tool_c"


@pytest.mark.asyncio
async def test_retry_on_429_and_no_retry_on_400(dummy_tool_spec: ToolSpec):
    """Assert that 429 triggers exponential backoff retry while 400 immediately raises LLMError."""
    mock_client = MagicMock()
    mock_models = MagicMock()
    mock_client.aio.models = mock_models

    # 1. Simulate 429 that succeeds on second try
    err_429 = errors.APIError(429, {"message": "Resource exhausted"})

    success_content = types.Content(
        role="model",
        parts=[types.Part.from_text(text="Success after retry")],
    )
    mock_response = MagicMock(candidates=[MagicMock(content=success_content)])

    mock_models.generate_content = AsyncMock(side_effect=[err_429, mock_response])

    session = GeminiSession(
        system="System",
        tools=[dummy_tool_spec],
        api_key="fake-key",
        client=mock_client,
    )

    turn = await session.send_user("Trigger 429 retry")
    assert turn.text == "Success after retry"
    assert mock_models.generate_content.call_count == 2

    # 2. Simulate 400 error (must not retry, call_count should be 1)
    err_400 = errors.APIError(400, {"message": "Bad request: invalid parameters"})
    mock_models.generate_content = AsyncMock(side_effect=err_400)

    session_fail = GeminiSession(
        system="System",
        tools=[dummy_tool_spec],
        api_key="fake-key",
        client=mock_client,
    )

    with pytest.raises(LLMError, match="Gemini API 400 error"):
        await session_fail.send_user("Trigger 400")
    assert mock_models.generate_content.call_count == 1


def test_thinking_level_minimal_rejected_before_api_call(dummy_tool_spec: ToolSpec):
    """Assert that thinking_level='minimal' is rejected at initialization before any API call."""
    with pytest.raises(ValueError, match="Thinking level 'minimal' is not supported"):
        GeminiSession(
            system="System",
            tools=[dummy_tool_spec],
            api_key="fake-key",
            thinking_level="minimal",
        )


def test_simplify_schema_fixture_validation():
    """Assert schema simplifier inlines $ref, removes title/default, and simplifies anyOf [X, null]."""
    fixture = {
        "$defs": {
            "Dimension": {
                "title": "Dimension",
                "type": "object",
                "properties": {
                    "width": {"title": "Width", "type": "number", "default": 10.0},
                    "height": {"title": "Height", "type": "number"},
                },
                "required": ["width"],
            }
        },
        "title": "WidgetSchema",
        "type": "object",
        "properties": {
            "dim": {"$ref": "#/$defs/Dimension"},
            "label": {
                "title": "WidgetLabel",
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": "Optional label",
            },
        },
        "required": ["dim"],
    }

    simplified = simplify_schema(fixture)
    assert_simple_schema(simplified)

    assert "$defs" not in simplified
    assert "title" not in simplified
    assert simplified["properties"]["dim"]["type"] == "object"
    assert "title" not in simplified["properties"]["dim"]["properties"]["width"]
    assert "default" not in simplified["properties"]["dim"]["properties"]["width"]
    assert simplified["properties"]["label"]["type"] == "string"
    assert simplified["properties"]["label"]["description"] == "Optional label"
