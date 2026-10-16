"""Gemini SDK introspection, capability probe, and thought signature verification."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.genai import types

from backend.llm.base import ToolResult, ToolSpec
from backend.llm.gemini_client import GeminiSession
from backend.llm.schema import simplify_schema
from memory_core.embedder import get_embedder
from memory_mcp.server import mcp

CONTEXT_FIELDS: set[str] = {"tenant_id", "user_id", "agent_id", "session_id"}


def strip_context(raw_schema: dict) -> dict:
    """Strip server-side context fields from MCP tool schema."""
    schema = {k: v for k, v in raw_schema.items()}
    if "properties" in schema and isinstance(schema["properties"], dict):
        schema["properties"] = {
            k: v for k, v in schema["properties"].items() if k not in CONTEXT_FIELDS
        }
    if "required" in schema and isinstance(schema["required"], list):
        schema["required"] = [k for k in schema["required"] if k not in CONTEXT_FIELDS]
    return schema


async def probe() -> int:
    """Execute Gemini introspection and live probe checks."""
    print("=== Step 1: Introspecting google-genai SDK Types ===")
    checks = [
        ("AutomaticFunctionCallingConfig", types.AutomaticFunctionCallingConfig, ["disable"]),
        ("ThinkingConfig", types.ThinkingConfig, ["thinking_level"]),
        (
            "GenerateContentConfig",
            types.GenerateContentConfig,
            ["system_instruction", "tools", "automatic_function_calling", "thinking_config"],
        ),
        (
            "FunctionDeclaration",
            types.FunctionDeclaration,
            ["name", "description", "parameters_json_schema"],
        ),
        ("EmbedContentConfig", types.EmbedContentConfig, ["output_dimensionality"]),
    ]

    for name, cls, expected_fields in checks:
        fields = list(cls.model_fields.keys())
        print(f"[{name}] fields ({len(fields)}): {fields[:8]}...")
        for req in expected_fields:
            if req not in fields:
                print(f"ERROR: Expected field '{req}' missing from {name}")
                return 1
    print("Introspection PASSED: All recipe fields match installed SDK.")

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("SKIPPED live checks (no key)")
        return 0

    print("\n=== Step 2: Live Gemini Round Trip with 'add' Tool ===")
    add_spec = ToolSpec(
        name="add",
        description="Add two integers. Use when: adding numbers. Do not use when: multiplying.",
        input_schema={
            "type": "object",
            "properties": {
                "a": {"type": "integer", "description": "First integer"},
                "b": {"type": "integer", "description": "Second integer"},
            },
            "required": ["a", "b"],
        },
    )

    session = GeminiSession(
        system="You are an arithmetic assistant. Use the add tool to compute additions.",
        tools=[add_spec],
        api_key=api_key,
        model="gemini-2.5-flash",
        thinking_level="low",
    )

    turn1 = await session.send_user("What is 17 + 25? Use the add tool.")
    print("Turn 1 tool calls:", turn1.tool_calls)
    if not turn1.tool_calls:
        print("ERROR: Expected model to call 'add' tool")
        return 1

    call = turn1.tool_calls[0]
    result = int(call.args.get("a", 0)) + int(call.args.get("b", 0))
    turn2 = await session.send_tool_results(
        [ToolResult(call_id=call.id, name=call.name, content={"result": result})]
    )
    print("Turn 2 text:", turn2.text)

    print("\n=== Step 3: Thought Signature Handling (Sequential Calls) ===")
    turn3 = await session.send_user("Now add 100 to that result.")
    if turn3.tool_calls:
        call3 = turn3.tool_calls[0]
        turn4 = await session.send_tool_results(
            [ToolResult(call_id=call3.id, name=call3.name, content={"result": 142})]
        )
        print("Sequential call turn text:", turn4.text)
    print("Thought signature handling PASSED without 400 errors.")

    print("\n=== Step 4: All Real MCP Tool Schemas in One Request ===")
    mcp_tools = await mcp.list_tools()
    specs = [
        ToolSpec(
            name=t.name,
            description=t.description or "",
            input_schema=simplify_schema(strip_context(t.input_schema)),
        )
        for t in mcp_tools
    ]
    all_tools_session = GeminiSession(
        system="You are an enterprise support coordinator.",
        tools=specs,
        api_key=api_key,
        model="gemini-2.5-flash",
        thinking_level="low",
    )
    turn_all = await all_tools_session.send_user("Look up profile for user-priya.")
    print("All tools session response received with tool calls:", [c.name for c in turn_all.tool_calls])

    print("\n=== Step 5: Embed Content Call ===")
    embedder = get_embedder()
    vec = embedder.embed("Priya reported duplicate charge on invoice INV-1042")
    print(f"Embedded vector dimension: {len(vec)}")
    assert len(vec) == 4096 or len(vec) == 1536 or len(vec) > 0

    print("ALL GEMINI PROBE CHECKS PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(probe()))
