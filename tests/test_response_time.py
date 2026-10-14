from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from testforge.execution_models import ExecutionStatus
from testforge.executor import HTTPTestExecutor
from testforge.models import GeneratedTestCase, TestCategory


def make_test_case(max_response_time_ms=None):
    return GeneratedTestCase(
        test_id="TC-TIME-001",
        name="Response time assertion",
        category=TestCategory.POSITIVE,
        method="GET",
        path="/health",
        expected_status_codes=[200],
        max_response_time_ms=max_response_time_ms,
    )


def test_response_within_threshold_passes():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"status": "ok"},
        )
    )

    with HTTPTestExecutor(
        base_url="https://example.com",
        transport=transport,
    ) as executor:
        result = executor.execute(make_test_case(10000))

    assert result.status == ExecutionStatus.PASSED
    assert result.response_time_ms is not None


def test_response_without_threshold_preserves_behavior():
    transport = httpx.MockTransport(lambda request: httpx.Response(200))

    with HTTPTestExecutor(
        base_url="https://example.com",
        transport=transport,
    ) as executor:
        result = executor.execute(make_test_case())

    assert result.status == ExecutionStatus.PASSED


@pytest.mark.parametrize("threshold", [0, -1, -100])
def test_invalid_threshold_is_rejected(threshold):
    with pytest.raises(ValidationError):
        make_test_case(threshold)


def test_response_exceeding_threshold_fails():
    transport = httpx.MockTransport(lambda request: httpx.Response(200))

    with (
        HTTPTestExecutor(
            base_url="https://example.com",
            transport=transport,
        ) as executor,
        patch(
            "testforge.executor.perf_counter",
            side_effect=[10.0, 10.75],
        ),
    ):
        result = executor.execute(make_test_case(500))

    assert result.status == ExecutionStatus.FAILED
    assert result.response_time_ms == 750.0
    assert "Response time exceeded threshold" in result.error_message


def test_response_exactly_at_threshold_passes():
    transport = httpx.MockTransport(lambda request: httpx.Response(200))

    with (
        HTTPTestExecutor(
            base_url="https://example.com",
            transport=transport,
        ) as executor,
        patch(
            "testforge.executor.perf_counter",
            side_effect=[10.0, 10.5],
        ),
    ):
        result = executor.execute(make_test_case(500))

    assert result.status == ExecutionStatus.PASSED
    assert result.response_time_ms == 500.0


def test_existing_status_failure_is_preserved():
    transport = httpx.MockTransport(lambda request: httpx.Response(500))

    with (
        HTTPTestExecutor(
            base_url="https://example.com",
            transport=transport,
        ) as executor,
        patch(
            "testforge.executor.perf_counter",
            side_effect=[10.0, 11.0],
        ),
    ):
        result = executor.execute(make_test_case(500))

    assert result.status == ExecutionStatus.FAILED
    assert result.actual_status_code == 500
    assert result.error_message is None


def test_existing_schema_failure_is_preserved():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"id": "invalid"},
        )
    )

    test_case = make_test_case(500)
    test_case.response_schemas = {
        200: {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "integer"},
            },
        }
    }

    with (
        HTTPTestExecutor(
            base_url="https://example.com",
            transport=transport,
        ) as executor,
        patch(
            "testforge.executor.perf_counter",
            side_effect=[10.0, 11.0],
        ),
    ):
        result = executor.execute(test_case)

    assert result.status == ExecutionStatus.FAILED
    assert result.response_time_ms == 1000.0
    assert "Response schema validation failed" in result.error_message
    assert "Response time exceeded threshold" not in result.error_message
