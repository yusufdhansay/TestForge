import pytest
from pydantic import ValidationError

from testforge.report_models import ExecutionSummary


def test_valid_execution_summary():
    summary = ExecutionSummary(
        total=10,
        passed=6,
        failed=2,
        unasserted=1,
        errors=1,
        pass_rate=60.0,
        average_response_time_ms=20.5,
        min_response_time_ms=5.0,
        max_response_time_ms=45.0,
        p95_response_time_ms=42.0,
    )

    assert summary.total == 10
    assert summary.passed == 6
    assert summary.pass_rate == 60.0
    assert summary.p95_response_time_ms == 42.0


def test_summary_without_timing_data():
    summary = ExecutionSummary(
        total=0,
        passed=0,
        failed=0,
        unasserted=0,
        errors=0,
        pass_rate=0.0,
    )

    assert summary.average_response_time_ms is None
    assert summary.p95_response_time_ms is None


def test_negative_counts_rejected():
    with pytest.raises(ValidationError):
        ExecutionSummary(
            total=-1,
            passed=0,
            failed=0,
            unasserted=0,
            errors=0,
            pass_rate=0.0,
        )


def test_invalid_pass_rate_rejected():
    with pytest.raises(ValidationError):
        ExecutionSummary(
            total=10,
            passed=10,
            failed=0,
            unasserted=0,
            errors=0,
            pass_rate=120.0,
        )
