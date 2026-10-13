from typing import Any


class UnsupportedSchemaError(ValueError):
    """Raised when a schema cannot be safely generated."""


def generate_value(schema: dict[str, Any]) -> Any:
    """Generate one deterministic value for a supported OpenAPI schema."""

    if not isinstance(schema, dict):
        raise UnsupportedSchemaError("Schema must be an object")

    unsupported_keywords = {
        "pattern",
        "format",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "uniqueItems",
        "contains",
        "minContains",
        "maxContains",
        "patternProperties",
        "additionalProperties",
        "propertyNames",
        "minProperties",
        "maxProperties",
        "dependentRequired",
        "dependentSchemas",
        "if",
        "then",
        "else",
    }

    found = unsupported_keywords.intersection(schema)

    if found:
        raise UnsupportedSchemaError(f"Unsupported schema constraints: {sorted(found)}")

    if any(key in schema for key in ("$ref", "oneOf", "anyOf", "allOf", "not")):
        raise UnsupportedSchemaError("Schema composition or references unsupported")

    if "const" in schema:
        return schema["const"]

    if "enum" in schema:
        values = schema["enum"]
        if not isinstance(values, list) or not values:
            raise UnsupportedSchemaError("Enum must be a nonempty list")
        return values[0]

    schema_type = schema.get("type")

    if schema_type == "string":
        min_length = schema.get("minLength", 0)
        max_length = schema.get("maxLength")

        if not isinstance(min_length, int) or min_length < 0:
            raise UnsupportedSchemaError("Invalid minLength")
        if max_length is not None and (
            not isinstance(max_length, int) or max_length < min_length
        ):
            raise UnsupportedSchemaError("Invalid maxLength")

        length = max(1, min_length)
        if max_length == 0:
            length = 0
        if max_length is not None and length > max_length:
            raise UnsupportedSchemaError("Cannot satisfy string constraints")

        return "a" * length

    if schema_type in ("integer", "number"):
        minimum = schema.get("minimum", 0)
        maximum = schema.get("maximum")

        if not isinstance(minimum, (int, float)) or isinstance(minimum, bool):
            raise UnsupportedSchemaError("Invalid minimum")
        if maximum is not None and (
            not isinstance(maximum, (int, float))
            or isinstance(maximum, bool)
            or maximum < minimum
        ):
            raise UnsupportedSchemaError("Invalid maximum")

        if schema_type == "integer":
            import math

            value = math.ceil(minimum)
        else:
            value = minimum

        if maximum is not None and value > maximum:
            raise UnsupportedSchemaError("Cannot satisfy numeric constraints")

        return value

    if schema_type == "boolean":
        return True

    if schema_type == "array":
        items = schema.get("items")
        if not isinstance(items, dict):
            raise UnsupportedSchemaError("Array items schema required")

        count = max(1, schema.get("minItems", 0))
        max_items = schema.get("maxItems")
        if max_items is not None and count > max_items:
            raise UnsupportedSchemaError("Cannot satisfy array constraints")

        return [generate_value(items) for _ in range(count)]

    if schema_type == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        if not isinstance(properties, dict) or not isinstance(required, list):
            raise UnsupportedSchemaError("Invalid object schema")

        missing = set(required) - set(properties)
        if missing:
            raise UnsupportedSchemaError(
                f"Missing definitions for required properties: {sorted(missing)}"
            )

        return {name: generate_value(properties[name]) for name in required}

    raise UnsupportedSchemaError(f"Unsupported schema type: {schema_type!r}")
