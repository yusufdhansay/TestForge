import json

import pytest

from testforge.parser import OpenAPIParser


def test_parse_valid_specification():
    parser = OpenAPIParser("examples/banking_api.json")
    specification = parser.parse()

    assert specification.title == "Banking API"
    assert specification.version == "1.0.0"
    assert specification.openapi_version == "3.1.0"
    assert len(specification.operations) == 3


def test_extract_http_methods():
    specification = OpenAPIParser("examples/banking_api.json").parse()

    methods = {operation.method for operation in specification.operations}

    assert methods == {"GET", "POST"}


def test_extract_path_parameters():
    specification = OpenAPIParser("examples/banking_api.json").parse()

    operation = next(
        operation
        for operation in specification.operations
        if operation.path == "/accounts/{id}"
    )

    assert len(operation.parameters) == 1
    assert operation.parameters[0].name == "id"
    assert operation.parameters[0].location == "path"
    assert operation.parameters[0].required is True


def test_extract_request_body():
    specification = OpenAPIParser("examples/banking_api.json").parse()

    operation = next(
        operation
        for operation in specification.operations
        if operation.method == "POST"
    )

    assert operation.request_body is not None
    assert "application/json" in operation.request_body["content"]


def test_missing_file():
    parser = OpenAPIParser("examples/nonexistent.json")

    with pytest.raises(FileNotFoundError):
        parser.parse()


def test_unsupported_version(tmp_path):
    specification = {
        "openapi": "2.0",
        "info": {
            "title": "Old API",
            "version": "1.0.0",
        },
        "paths": {},
    }

    file_path = tmp_path / "old_api.json"
    file_path.write_text(
        json.dumps(specification),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Only OpenAPI",
    ):
        OpenAPIParser(file_path).parse()


def test_invalid_json(tmp_path):
    file_path = tmp_path / "invalid.json"
    file_path.write_text(
        "{invalid json}",
        encoding="utf-8",
    )

    with pytest.raises(json.JSONDecodeError):
        OpenAPIParser(file_path).parse()


def test_operation_parameter_overrides_path_parameter(tmp_path):
    specification = {
        "openapi": "3.1.0",
        "info": {
            "title": "Override Test",
            "version": "1.0.0",
        },
        "paths": {
            "/items/{id}": {
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "get": {
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        }
                    ],
                    "responses": {"200": {"description": "Success"}},
                },
            }
        },
    }

    file_path = tmp_path / "override.json"
    file_path.write_text(
        json.dumps(specification),
        encoding="utf-8",
    )

    result = OpenAPIParser(file_path).parse()

    parameters = result.operations[0].parameters

    assert len(parameters) == 1
    assert parameters[0].name == "id"
    assert parameters[0].schema_definition == {"type": "integer"}
