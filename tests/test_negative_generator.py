from testforge.negative_generator import generate_negative_bodies


def test_missing_required_fields():
    schema = {
        "type": "object",
        "required": ["name", "balance"],
        "properties": {
            "name": {"type": "string"},
            "balance": {"type": "number"},
        },
    }

    cases = dict(generate_negative_bodies(schema))

    assert cases["missing_required_name"] == {"balance": 0}
    assert cases["missing_required_balance"] == {"name": "a"}


def test_invalid_field_types():
    schema = {
        "type": "object",
        "required": ["name", "balance"],
        "properties": {
            "name": {"type": "string"},
            "balance": {"type": "number"},
        },
    }

    cases = dict(generate_negative_bodies(schema))

    assert cases["invalid_type_name"] == {
        "name": 123,
        "balance": 0,
    }

    assert cases["invalid_type_balance"] == {
        "name": "a",
        "balance": "invalid",
    }


def test_non_object_schema():
    assert generate_negative_bodies({"type": "string"}) == []


def test_each_case_has_one_mutation():
    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string"},
        },
    }

    cases = dict(generate_negative_bodies(schema))

    assert len(cases) == 2
    assert cases["missing_required_name"] == {}
    assert cases["invalid_type_name"] == {"name": 123}


def test_optional_fields_are_not_mutated():
    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string"},
            "nickname": {"type": "string"},
        },
    }

    cases = dict(generate_negative_bodies(schema))

    assert len(cases) == 2
    assert "missing_required_nickname" not in cases
    assert "invalid_type_nickname" not in cases
