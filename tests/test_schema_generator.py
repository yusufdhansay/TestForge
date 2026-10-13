import pytest

from testforge.schema_generator import (
    UnsupportedSchemaError,
    generate_value,
)


def test_generate_string():
    assert generate_value({"type": "string", "minLength": 3}) == "aaa"


def test_generate_integer():
    assert generate_value({"type": "integer", "minimum": 2}) == 2


def test_generate_object():
    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
        },
    }

    assert generate_value(schema) == {"name": "a"}


def test_generate_array():
    assert generate_value(
        {"type": "array", "items": {"type": "boolean"}, "minItems": 2}
    ) == [True, True]


def test_reject_reference():
    with pytest.raises(UnsupportedSchemaError):
        generate_value({"$ref": "#/components/schemas/Account"})


def test_reject_impossible_constraint():
    with pytest.raises(UnsupportedSchemaError):
        generate_value({"type": "string", "minLength": 5, "maxLength": 2})


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "string", "pattern": "^[A-Z]+$"},
        {"type": "string", "format": "email"},
        {"type": "integer", "exclusiveMinimum": 0},
        {"type": "integer", "multipleOf": 5},
        {"type": "array", "items": {"type": "integer"}, "uniqueItems": True},
    ],
)
def test_reject_unsupported_constraints(schema):
    with pytest.raises(UnsupportedSchemaError):
        generate_value(schema)


def test_generate_nested_required_object():
    schema = {
        "type": "object",
        "required": ["profile"],
        "properties": {
            "profile": {
                "type": "object",
                "required": ["age"],
                "properties": {"age": {"type": "integer", "minimum": 18}},
            }
        },
    }

    assert generate_value(schema) == {"profile": {"age": 18}}
