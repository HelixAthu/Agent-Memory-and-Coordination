"""Tests for tool schema simplicity, validation, and Gemini compatibility."""

from __future__ import annotations

import pytest

from backend.llm.schema import assert_simple_schema, simplify_schema
from memory_mcp.server import mcp

CONTEXT_FIELDS: set[str] = {"tenant_id", "user_id", "agent_id", "session_id"}


def strip_context_fields(raw_schema: dict) -> dict:
    """Remove context fields from tool input schema for LLM exposure."""
    schema = {k: v for k, v in raw_schema.items()}
    if "properties" in schema and isinstance(schema["properties"], dict):
        schema["properties"] = {
            k: v for k, v in schema["properties"].items() if k not in CONTEXT_FIELDS
        }
    if "required" in schema and isinstance(schema["required"], list):
        schema["required"] = [k for k in schema["required"] if k not in CONTEXT_FIELDS]
    return schema


@pytest.mark.asyncio
async def test_all_mcp_tool_schemas_are_simple():
    """Verify that all 16 MCP tool schemas satisfy Gemini simple schema requirements."""
    tools = await mcp.list_tools()
    assert len(tools) == 16

    for tool in tools:
        assert tool.description is not None
        assert "Use when:" in tool.description
        assert "Do not use when:" in tool.description

        stripped = strip_context_fields(tool.input_schema)
        simplified = simplify_schema(stripped)
        assert_simple_schema(simplified)


def test_simplify_schema_inlines_refs_and_strips_metadata():
    """Verify ref inlining, title/default removal, and anyOf null flattening."""
    raw = {
        "$defs": {
            "Address": {
                "title": "Address",
                "type": "object",
                "properties": {
                    "city": {"title": "City", "type": "string", "default": "Pune"},
                },
            }
        },
        "title": "UserPayload",
        "type": "object",
        "properties": {
            "addr": {"$ref": "#/$defs/Address"},
            "optional_name": {
                "title": "Name",
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": "User full name",
            },
        },
        "required": ["addr"],
    }

    simplified = simplify_schema(raw)
    assert_simple_schema(simplified)

    assert "$defs" not in simplified
    assert "title" not in simplified
    assert simplified["properties"]["addr"]["type"] == "object"
    assert "default" not in simplified["properties"]["addr"]["properties"]["city"]
    assert "title" not in simplified["properties"]["addr"]["properties"]["city"]
    assert simplified["properties"]["optional_name"]["type"] == "string"
    assert simplified["properties"]["optional_name"]["description"] == "User full name"


def test_assert_simple_schema_rejects_forbidden_keys():
    """Verify that assert_simple_schema raises AssertionError for unsupported keys."""
    bad_schema = {
        "type": "object",
        "properties": {
            "val": {"oneOf": [{"type": "string"}, {"type": "integer"}]},
        },
    }
    with pytest.raises(AssertionError, match="Forbidden key 'oneOf'"):
        assert_simple_schema(bad_schema)
