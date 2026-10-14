from testforge.coverage import ContractCoverageAnalyzer
from testforge.execution_models import ExecutionResult, ExecutionStatus
from testforge.models import (
    APISpecification,
    GeneratedTestCase,
    TestCategory,
)


def make_specification():
    return APISpecification.model_validate(
        {
            "openapi_version": "3.0.3",
            "title": "Coverage Test API",
            "version": "1.0.0",
            "operations": [
                {
                    "method": "GET",
                    "path": "/users",
                    "responses": {"200": {"description": "OK"}},
                },
                {
                    "method": "POST",
                    "path": "/users",
                    "responses": {"201": {"description": "Created"}},
                },
                {
                    "method": "DELETE",
                    "path": "/users/{id}",
                    "responses": {"204": {"description": "Deleted"}},
                },
            ],
        }
    )


def make_test_case(test_id, method, path):
    return GeneratedTestCase(
        test_id=test_id,
        name=f"{method} {path}",
        category=TestCategory.POSITIVE,
        method=method,
        path=path,
        expected_status_codes=[200],
    )


def make_result(
    test_id,
    status=ExecutionStatus.PASSED,
    actual_status_code=200,
):
    return ExecutionResult(
        test_id=test_id,
        status=status,
        actual_status_code=actual_status_code,
        expected_status_codes=[200],
    )


def test_full_generated_and_executed_coverage():
    specification = make_specification()

    test_cases = [
        make_test_case("TC-001", "GET", "/users"),
        make_test_case("TC-002", "POST", "/users"),
        make_test_case("TC-003", "DELETE", "/users/{id}"),
    ]

    results = [
        make_result("TC-001"),
        make_result("TC-002", actual_status_code=201),
        make_result("TC-003", actual_status_code=204),
    ]

    report = ContractCoverageAnalyzer().analyze(
        specification,
        test_cases,
        results,
    )

    assert report.total_operations == 3
    assert report.generated_operations == 3
    assert report.executed_operations == 3
    assert report.generated_coverage_percent == 100.0
    assert report.executed_coverage_percent == 100.0
    assert report.untested_operations == []


def test_partial_generated_coverage():
    specification = make_specification()

    test_cases = [
        make_test_case("TC-001", "GET", "/users"),
        make_test_case("TC-002", "POST", "/users"),
    ]

    report = ContractCoverageAnalyzer().analyze(
        specification,
        test_cases,
    )

    assert report.total_operations == 3
    assert report.generated_operations == 2
    assert report.executed_operations == 0
    assert report.generated_coverage_percent == 66.67
    assert report.executed_coverage_percent == 0.0


def test_partial_executed_coverage():
    specification = make_specification()

    test_cases = [
        make_test_case("TC-001", "GET", "/users"),
        make_test_case("TC-002", "POST", "/users"),
        make_test_case("TC-003", "DELETE", "/users/{id}"),
    ]

    results = [
        make_result("TC-001"),
    ]

    report = ContractCoverageAnalyzer().analyze(
        specification,
        test_cases,
        results,
    )

    assert report.generated_coverage_percent == 100.0
    assert report.executed_coverage_percent == 33.33
    assert report.executed_operations == 1

    assert "POST /users" in report.untested_operations
    assert "DELETE /users/{id}" in report.untested_operations


def test_blocked_operation_does_not_count_as_executed():
    specification = make_specification()

    test_cases = [
        make_test_case("TC-001", "POST", "/users"),
    ]

    results = [
        make_result(
            "TC-001",
            status=ExecutionStatus.ERROR,
            actual_status_code=None,
        )
    ]

    report = ContractCoverageAnalyzer().analyze(
        specification,
        test_cases,
        results,
    )

    assert report.generated_operations == 1
    assert report.executed_operations == 0
    assert report.total_executed_tests == 0


def test_failed_assertion_still_counts_as_executed():
    specification = make_specification()

    test_cases = [
        make_test_case("TC-001", "GET", "/users"),
    ]

    results = [
        make_result(
            "TC-001",
            status=ExecutionStatus.FAILED,
            actual_status_code=500,
        )
    ]

    report = ContractCoverageAnalyzer().analyze(
        specification,
        test_cases,
        results,
    )

    assert report.executed_operations == 1
    assert report.total_executed_tests == 1


def test_multiple_tests_count_as_one_covered_operation():
    specification = make_specification()

    test_cases = [
        make_test_case("TC-001", "GET", "/users"),
        make_test_case("TC-002", "GET", "/users"),
    ]

    results = [
        make_result("TC-001"),
        make_result("TC-002"),
    ]

    report = ContractCoverageAnalyzer().analyze(
        specification,
        test_cases,
        results,
    )

    assert report.generated_operations == 1
    assert report.executed_operations == 1
    assert report.total_generated_tests == 2
    assert report.total_executed_tests == 2

    get_operation = next(
        operation for operation in report.operations if operation.method == "GET"
    )

    assert get_operation.generated_tests == 2
    assert get_operation.executed_tests == 2


def test_method_level_coverage():
    specification = make_specification()

    test_cases = [
        make_test_case("TC-001", "GET", "/users"),
        make_test_case("TC-002", "POST", "/users"),
    ]

    results = [
        make_result("TC-001"),
    ]

    report = ContractCoverageAnalyzer().analyze(
        specification,
        test_cases,
        results,
    )

    methods = {method.method: method for method in report.methods}

    assert methods["GET"].generated_coverage_percent == 100.0
    assert methods["GET"].executed_coverage_percent == 100.0

    assert methods["POST"].generated_coverage_percent == 100.0
    assert methods["POST"].executed_coverage_percent == 0.0

    assert methods["DELETE"].generated_coverage_percent == 0.0


def test_unknown_execution_result_is_ignored():
    specification = make_specification()

    report = ContractCoverageAnalyzer().analyze(
        specification,
        [],
        [
            make_result("UNKNOWN-TEST"),
        ],
    )

    assert report.executed_operations == 0
    assert report.total_executed_tests == 0


def test_empty_specification_has_zero_coverage():
    specification = APISpecification.model_validate(
        {
            "openapi_version": "3.0.3",
            "title": "Empty API",
            "version": "1.0.0",
            "operations": [],
        }
    )

    report = ContractCoverageAnalyzer().analyze(
        specification,
        [],
        [],
    )

    assert report.total_operations == 0
    assert report.generated_operations == 0
    assert report.executed_operations == 0
    assert report.generated_coverage_percent == 0.0
    assert report.executed_coverage_percent == 0.0
    assert report.methods == []
    assert report.untested_operations == []
