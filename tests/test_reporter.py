from testforge.execution_models import ExecutionResult, ExecutionStatus
from testforge.reporter import ExecutionReporter


def make_result(
    test_id: str,
    status: ExecutionStatus,
    response_time_ms: float | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        test_id=test_id,
        status=status,
        response_time_ms=response_time_ms,
    )


def test_empty_results():
    summary = ExecutionReporter().summarize([])

    assert summary.total == 0
    assert summary.pass_rate == 0.0
    assert summary.average_response_time_ms is None
    assert summary.p95_response_time_ms is None


def test_status_counts():
    results = [
        make_result("TC-1", ExecutionStatus.PASSED),
        make_result("TC-2", ExecutionStatus.PASSED),
        make_result("TC-3", ExecutionStatus.FAILED),
        make_result("TC-4", ExecutionStatus.UNASSERTED),
        make_result("TC-5", ExecutionStatus.ERROR),
    ]

    summary = ExecutionReporter().summarize(results)

    assert summary.total == 5
    assert summary.passed == 2
    assert summary.failed == 1
    assert summary.unasserted == 1
    assert summary.errors == 1
    assert summary.pass_rate == 40.0


def test_response_time_statistics():
    results = [
        make_result(
            f"TC-{index}",
            ExecutionStatus.PASSED,
            response_time_ms=float(index * 10),
        )
        for index in range(1, 21)
    ]

    summary = ExecutionReporter().summarize(results)

    assert summary.average_response_time_ms == 105.0
    assert summary.min_response_time_ms == 10.0
    assert summary.max_response_time_ms == 200.0
    assert summary.p95_response_time_ms == 190.0


def test_missing_response_times_excluded():
    results = [
        make_result("TC-1", ExecutionStatus.PASSED, 10.0),
        make_result("TC-2", ExecutionStatus.ERROR),
        make_result("TC-3", ExecutionStatus.PASSED, 30.0),
    ]

    summary = ExecutionReporter().summarize(results)

    assert summary.total == 3
    assert summary.average_response_time_ms == 20.0
    assert summary.min_response_time_ms == 10.0
    assert summary.max_response_time_ms == 30.0


def test_unasserted_results_not_counted_as_passed():
    results = [
        make_result("TC-1", ExecutionStatus.PASSED),
        make_result("TC-2", ExecutionStatus.UNASSERTED),
    ]

    summary = ExecutionReporter().summarize(results)

    assert summary.pass_rate == 50.0
    assert summary.passed == 1


def test_summary_is_deterministic():
    results = [
        make_result("TC-1", ExecutionStatus.PASSED, 30.0),
        make_result("TC-2", ExecutionStatus.FAILED, 10.0),
        make_result("TC-3", ExecutionStatus.ERROR, 20.0),
    ]

    reporter = ExecutionReporter()

    first = reporter.summarize(results)
    second = reporter.summarize(list(reversed(results)))

    assert first == second
