"""Schema simplifier and validator ensuring strict tool schemas for LLM function calling."""

from __future__ import annotations

import copy
from typing import Any

ALLOWED_SCHEMA_KEYS: set[str] = {
    "type",
    "properties",
    "required",
    "enum",
    "items",
    "description",
    "minimum",
    "maximum",
}


def simplify_schema(raw_schema: dict[str, Any]) -> dict[str, Any]:
    """Simplify JSON Schema by inlining defs, stripping disfavored keys, and flattening anyOf nulls."""
    schema = copy.deepcopy(raw_schema)
    defs = schema.pop("$defs", None) or schema.pop("definitions", None) or {}

    def _resolve_refs(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_path = node["$ref"]
                def_key = ref_path.split("/")[-1]
                if def_key in defs:
                    resolved = copy.deepcopy(defs[def_key])
                    return _resolve_refs(resolved)
            return {k: _resolve_refs(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_resolve_refs(item) for item in node]
        return node

    schema = _resolve_refs(schema)

    def _clean_node(node: Any) -> Any:
        if not isinstance(node, dict):
            if isinstance(node, list):
                return [_clean_node(item) for item in node]
            return node

        # Flatten anyOf: [X, {type: "null"}] or [{type: "null"}, X] to X
        if "anyOf" in node:
            any_of = node["anyOf"]
            non_null = [item for item in any_of if isinstance(item, dict) and item.get("type") != "null"]
            if len(non_null) == 1:
                replacement = _clean_node(non_null[0])
                if isinstance(replacement, dict):
                    # Retain description from outer node if present
                    if "description" in node and "description" not in replacement:
                        replacement["description"] = node["description"]
                    return replacement

        cleaned: dict[str, Any] = {}
        for k, v in node.items():
            if k in ("title", "default", "$defs", "definitions", "additionalProperties"):
                continue
            if k in ALLOWED_SCHEMA_KEYS:
                if k == "properties" and isinstance(v, dict):
                    cleaned[k] = {pk: _clean_node(pv) for pk, pv in v.items()}
                elif k == "items":
                    cleaned[k] = _clean_node(v)
                else:
                    cleaned[k] = v

        return cleaned

    return _clean_node(schema)


def assert_simple_schema(schema: dict[str, Any]) -> None:
    """Validate that a schema strictly adheres to Gemini-supported JSON schema constraints."""

    def _validate(node: Any, path: str = "root") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k not in ALLOWED_SCHEMA_KEYS:
                    raise AssertionError(f"Forbidden key '{k}' found at schema path '{path}'")
                if k == "properties" and isinstance(v, dict):
                    for prop_name, prop_schema in v.items():
                        _validate(prop_schema, f"{path}.properties.{prop_name}")
                elif k == "items":
                    _validate(v, f"{path}.items")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                _validate(item, f"{path}[{i}]")

    _validate(schema)
