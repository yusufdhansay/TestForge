import json

import httpx

from testforge.execution_models import ExecutionStatus
from testforge.executor import HTTPTestExecutor
from testforge.generator import ContractTestGenerator
from testforge.html_reporter import HTMLReportExporter
from testforge.json_reporter import JSONReportExporter
from testforge.models import TestCategory
from testforge.parser import OpenAPIParser
from testforge.reporter import ExecutionReporter


def test_negative_assertions_flow_through_reporting(tmp_path):
    specification = OpenAPIParser("examples/banking_api.json").parse()

    # Add a documented validation response to the parsed specification.
    post_operation = next(
        operation
        for operation in specification.operations
        if operation.method.upper() == "POST" and operation.path == "/accounts"
    )

    post_operation.responses["422"] = {"description": "Request validation failed"}

    test_cases = ContractTestGenerator(specification).generate()

    negative_cases = [
        case for case in test_cases if case.category == TestCategory.NEGATIVE
    ]

    assert len(test_cases) == 7
    assert len(negative_cases) == 4

    assert all(case.expected_status_codes == [422] for case in negative_cases)
    assert all(
        case.response_expectation is not None
        and case.response_expectation.source == "openapi"
        for case in negative_cases
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"accounts": []})

        if request.method == "POST":
            payload = json.loads(request.content)

            if (
                isinstance(payload, dict)
                and isinstance(payload.get("name"), str)
                and isinstance(payload.get("balance"), (int, float))
                and not isinstance(payload.get("balance"), bool)
            ):
                return httpx.Response(
                    201,
                    json={"id": "acc-001"},
                )

            return httpx.Response(
                422,
                json={"detail": "Validation error"},
            )

        return httpx.Response(405)

    transport = httpx.MockTransport(handler)

    with HTTPTestExecutor(
        base_url="https://banking.test",
        transport=transport,
        allow_state_changes=True,
    ) as executor:
        results = [executor.execute(test_case) for test_case in test_cases]

    summary = ExecutionReporter().summarize(results)

    assert summary.total == 7
    assert summary.passed == 7
    assert summary.failed == 0
    assert summary.unasserted == 0
    assert summary.errors == 0
    assert summary.pass_rate == 100.0

    for case, result in zip(test_cases, results, strict=True):
        if case.category == TestCategory.NEGATIVE:
            assert result.status == ExecutionStatus.PASSED
            assert result.actual_status_code == 422

    json_path = tmp_path / "negative-report.json"
    html_path = tmp_path / "negative-report.html"

    JSONReportExporter().export(results, json_path)
    HTMLReportExporter().export(results, html_path)

    json_data = json.loads(json_path.read_text(encoding="utf-8"))
    html_data = html_path.read_text(encoding="utf-8")

    assert json_data["summary"]["passed"] == 7
    assert json_data["summary"]["unasserted"] == 0
    assert len(json_data["results"]) == 7

    assert "TestForge Execution Report" in html_data
    assert "100.00%" in html_data
