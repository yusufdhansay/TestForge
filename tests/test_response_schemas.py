from testforge.generator import ContractTestGenerator, extract_response_schemas
from testforge.models import APIOperation, APISpecification


def test_extract_response_schemas():
    responses = {
        "200": {
            "description": "Success",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["id"],
                        "properties": {"id": {"type": "integer"}},
                    }
                }
            },
        },
        "400": {
            "description": "Bad request",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {"error": {"type": "string"}},
                    }
                }
            },
        },
        "404": {"description": "Not found"},
        "default": {"description": "Default response"},
    }

    schemas = extract_response_schemas(responses)

    assert set(schemas) == {200, 400}
    assert schemas[200]["properties"]["id"]["type"] == "integer"
    assert schemas[400]["properties"]["error"]["type"] == "string"


def test_generator_attaches_response_schemas():
    specification = APISpecification(
        title="Schema Test API",
        version="1.0.0",
        openapi_version="3.0.3",
        operations=[
            APIOperation(
                method="GET",
                path="/users",
                responses={
                    "200": {
                        "description": "Success",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"id": {"type": "integer"}},
                                }
                            }
                        },
                    }
                },
            )
        ],
    )

    test_cases = ContractTestGenerator(specification).generate()

    assert len(test_cases) == 1
    assert 200 in test_cases[0].response_schemas
    assert test_cases[0].response_schemas[200]["properties"]["id"]["type"] == "integer"
