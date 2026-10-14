import httpx

from testforge.execution_models import ExecutionStatus
from testforge.executor import HTTPTestExecutor
from testforge.models import GeneratedTestCase, TestCategory

RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["id", "name"],
    "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string"},
    },
}


def execute_response(body, schema=RESPONSE_SCHEMA):
    def handler(request):
        return httpx.Response(200, json=body)

    test_case = GeneratedTestCase(
        test_id="TC-SCHEMA-001",
        name="Validate user response",
        category=TestCategory.POSITIVE,
        method="GET",
        path="/users/1",
        expected_status_codes=[200],
        response_schemas={200: schema},
    )

    with HTTPTestExecutor(
        base_url="https://example.com",
        transport=httpx.MockTransport(handler),
    ) as executor:
        return executor.execute(test_case)


def test_valid_response_passes():
    result = execute_response({"id": 1, "name": "Alice"})

    assert result.status == ExecutionStatus.PASSED
    assert result.error_message is None


def test_incorrect_field_type_fails():
    result = execute_response({"id": "1", "name": "Alice"})

    assert result.status == ExecutionStatus.FAILED
    assert "schema validation failed" in result.error_message.lower()


def test_missing_required_field_fails():
    result = execute_response({"id": 1})

    assert result.status == ExecutionStatus.FAILED
    assert "name" in result.error_message


def test_invalid_schema_returns_error():
    result = execute_response(
        {"id": 1, "name": "Alice"},
        schema={"type": "not-a-valid-type"},
    )

    assert result.status == ExecutionStatus.ERROR
    assert "Invalid response schema" in result.error_message


def test_response_without_schema_preserves_status_check():
    result = execute_response(
        {"unexpected": "data"},
        schema={},
    )

    assert result.status == ExecutionStatus.PASSED


def test_malformed_json_response_fails():
    def handler(request):
        return httpx.Response(
            200,
            content=b'{"id": 1, "name":',
            headers={"Content-Type": "application/json"},
        )

    test_case = GeneratedTestCase(
        test_id="TC-SCHEMA-002",
        name="Malformed JSON response",
        category=TestCategory.POSITIVE,
        method="GET",
        path="/users/1",
        expected_status_codes=[200],
        response_schemas={200: RESPONSE_SCHEMA},
    )

    with HTTPTestExecutor(
        base_url="https://example.com",
        transport=httpx.MockTransport(handler),
    ) as executor:
        result = executor.execute(test_case)

    assert result.status == ExecutionStatus.FAILED
    assert "Invalid JSON response" in result.error_message


def test_actual_status_code_selects_matching_schema():
    def handler(request):
        return httpx.Response(
            400,
            json={"error": "Invalid request"},
        )

    test_case = GeneratedTestCase(
        test_id="TC-SCHEMA-003",
        name="Status-specific response schema",
        category=TestCategory.NEGATIVE,
        method="GET",
        path="/users/invalid",
        expected_status_codes=[400],
        response_schemas={
            200: RESPONSE_SCHEMA,
            400: {
                "type": "object",
                "required": ["error"],
                "properties": {
                    "error": {"type": "string"},
                },
            },
        },
    )

    with HTTPTestExecutor(
        base_url="https://example.com",
        transport=httpx.MockTransport(handler),
    ) as executor:
        result = executor.execute(test_case)

    assert result.status == ExecutionStatus.PASSED
    assert result.error_message is None


def test_nullable_response_property_passes():
    schema = {
        "type": "object",
        "required": ["id", "nickname"],
        "properties": {
            "id": {"type": "integer"},
            "nickname": {
                "type": "string",
                "nullable": True,
            },
        },
    }

    result = execute_response(
        {"id": 1, "nickname": None},
        schema=schema,
    )

    assert result.status == ExecutionStatus.PASSED


def test_incorrect_content_type_fails():
    def handler(request):
        return httpx.Response(
            200,
            content=b'{"id": 1, "name": "Alice"}',
            headers={"Content-Type": "text/plain"},
        )

    test_case = GeneratedTestCase(
        test_id="TC-SCHEMA-004",
        name="Incorrect response content type",
        category=TestCategory.POSITIVE,
        method="GET",
        path="/users/1",
        expected_status_codes=[200],
        response_schemas={200: RESPONSE_SCHEMA},
    )

    with HTTPTestExecutor(
        base_url="https://example.com",
        transport=httpx.MockTransport(handler),
    ) as executor:
        result = executor.execute(test_case)

    assert result.status == ExecutionStatus.FAILED
    assert "Content-Type" in result.error_message


def test_json_content_type_with_charset_passes():
    def handler(request):
        return httpx.Response(
            200,
            json={"id": 1, "name": "Alice"},
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

    test_case = GeneratedTestCase(
        test_id="TC-SCHEMA-005",
        name="JSON content type with charset",
        category=TestCategory.POSITIVE,
        method="GET",
        path="/users/1",
        expected_status_codes=[200],
        response_schemas={200: RESPONSE_SCHEMA},
    )

    with HTTPTestExecutor(
        base_url="https://example.com",
        transport=httpx.MockTransport(handler),
    ) as executor:
        result = executor.execute(test_case)

    assert result.status == ExecutionStatus.PASSED


def test_204_without_schema_passes():
    def handler(request):
        return httpx.Response(204)

    test_case = GeneratedTestCase(
        test_id="TC-SCHEMA-006",
        name="No-content response",
        category=TestCategory.POSITIVE,
        method="GET",
        path="/users/1",
        expected_status_codes=[204],
    )

    with HTTPTestExecutor(
        base_url="https://example.com",
        transport=httpx.MockTransport(handler),
    ) as executor:
        result = executor.execute(test_case)

    assert result.status == ExecutionStatus.PASSED
    assert result.error_message is None


def test_204_with_declared_json_schema_fails():
    def handler(request):
        return httpx.Response(204)

    test_case = GeneratedTestCase(
        test_id="TC-SCHEMA-007",
        name="Missing declared JSON response",
        category=TestCategory.POSITIVE,
        method="GET",
        path="/users/1",
        expected_status_codes=[204],
        response_schemas={204: RESPONSE_SCHEMA},
    )

    with HTTPTestExecutor(
        base_url="https://example.com",
        transport=httpx.MockTransport(handler),
    ) as executor:
        result = executor.execute(test_case)

    assert result.status == ExecutionStatus.FAILED
    assert result.error_message is not None
