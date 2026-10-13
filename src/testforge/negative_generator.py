from copy import deepcopy
from typing import Any

from testforge.schema_generator import generate_value


def generate_negative_bodies(
    schema: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """Generate single-fault negative request bodies for object schemas."""

    if schema.get("type") != "object":
        return []

    valid_body = generate_value(schema)
    required = schema.get("required", [])
    properties = schema.get("properties", {})

    negative_cases = []

    for field in required:
        invalid_body = deepcopy(valid_body)
        invalid_body.pop(field, None)

        negative_cases.append((f"missing_required_{field}", invalid_body))

    invalid_values = {
        "string": 123,
        "integer": "invalid",
        "number": "invalid",
        "boolean": "invalid",
        "array": "invalid",
        "object": "invalid",
    }

    for field in required:
        field_schema = properties[field]
        field_type = field_schema.get("type")

        if field_type not in invalid_values:
            continue

        invalid_body = deepcopy(valid_body)
        invalid_body[field] = invalid_values[field_type]

        negative_cases.append((f"invalid_type_{field}", invalid_body))

    return negative_cases
