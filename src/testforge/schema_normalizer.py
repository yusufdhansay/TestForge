from copy import deepcopy
from typing import Any


def normalize_openapi_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Convert OpenAPI 3.0 nullable declarations to JSON Schema types."""

    normalized = deepcopy(schema)

    def normalize(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                normalize(item)
            return

        if not isinstance(node, dict):
            return

        if node.get("nullable") is True and isinstance(node.get("type"), str):
            node["type"] = [node["type"], "null"]

        node.pop("nullable", None)

        for key, value in node.items():
            if key in {
                "properties",
                "patternProperties",
                "$defs",
                "definitions",
            } and isinstance(value, dict):
                for child_schema in value.values():
                    normalize(child_schema)
            elif key in {
                "items",
                "additionalProperties",
                "not",
                "if",
                "then",
                "else",
            } or key in {"allOf", "anyOf", "oneOf", "prefixItems"}:
                normalize(value)

    normalize(normalized)
    return normalized
