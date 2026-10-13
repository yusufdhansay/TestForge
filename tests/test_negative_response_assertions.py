import httpx
import pytest

from testforge.execution_models import ExecutionStatus
from testforge.executor import HTTPTestExecutor
from testforge.models import (
    GeneratedTestCase,
    ResponseExpectation,
    TestCategory,
)


def make_negative_case(expected_status_codes):
    return GeneratedTestCase(
        test_id="TC-NEG-001",
        name="POST /accounts - missing required field",
        category=TestCategory.NEGATIVE,
        method="POST",
        path="/accounts",
        request_body={},
        expected_status_codes=expected_status_codes,
        response_expectation=(
            ResponseExpectation(
                source="openapi",
                description="Validation error",
            )
            if expected_status_codes
            else None
        ),
    )


@pytest.mark.parametrize(
    ("expected", "actual", "expected_result"),
    [
        ([422], 422, ExecutionStatus.PASSED),
        ([422], 400, ExecutionStatus.FAILED),
        ([400, 422], 400, ExecutionStatus.PASSED),
        ([400, 422], 422, ExecutionStatus.PASSED),
        ([], 422, ExecutionStatus.UNASSERTED),
        ([], 201, ExecutionStatus.UNASSERTED),
    ],
)
def test_negative_response_classification(expected, actual, expected_result):
    case = make_negative_case(expected)

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            actual,
            json={"detail": "Validation error"},
        )
    )

    with HTTPTestExecutor(
        base_url="https://banking.test",
        transport=transport,
        allow_state_changes=True,
    ) as executor:
        result = executor.execute(case)

    assert result.status == expected_result
    assert result.actual_status_code == actual
    assert result.expected_status_codes == expected


def test_negative_test_requires_state_change_approval():
    case = make_negative_case([422])

    transport = httpx.MockTransport(lambda request: httpx.Response(422))

    with HTTPTestExecutor(
        base_url="https://banking.test",
        transport=transport,
        allow_state_changes=False,
    ) as executor:
        result = executor.execute(case)

    assert result.status == ExecutionStatus.ERROR
    assert result.actual_status_code is None
    assert "approval" in result.error_message.lower()
