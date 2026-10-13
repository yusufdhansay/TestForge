from testforge.execution_models import (
    ExecutionResult,
    ExecutionStatus,
)


def test_passed_execution_result():
    result = ExecutionResult(
        test_id="TC-0001",
        status=ExecutionStatus.PASSED,
        actual_status_code=200,
        expected_status_codes=[200],
        response_time_ms=12.5,
    )

    assert result.status == ExecutionStatus.PASSED
    assert result.actual_status_code == 200
    assert result.response_time_ms == 12.5


def test_unasserted_execution_result():
    result = ExecutionResult(
        test_id="TC-0002",
        status=ExecutionStatus.UNASSERTED,
        actual_status_code=422,
        expected_status_codes=[],
    )

    assert result.status == ExecutionStatus.UNASSERTED
    assert result.expected_status_codes == []


def test_execution_error():
    result = ExecutionResult(
        test_id="TC-0003",
        status=ExecutionStatus.ERROR,
        error_message="Connection failed",
    )

    assert result.status == ExecutionStatus.ERROR
    assert result.actual_status_code is None
