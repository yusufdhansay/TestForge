import json

import httpx

from testforge.executor import HTTPTestExecutor
from testforge.generator import ContractTestGenerator
from testforge.html_reporter import HTMLReportExporter
from testforge.json_reporter import JSONReportExporter
from testforge.parser import OpenAPIParser
from testforge.reporter import ExecutionReporter


def test_complete_reporting_pipeline(tmp_path):
    specification = OpenAPIParser("examples/banking_api.json").parse()

    test_cases = ContractTestGenerator(specification).generate()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"balance": 1000},
            )

        if request.method == "POST" and request.url.path == "/accounts":
            try:
                payload = json.loads(request.content)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return httpx.Response(
                    422,
                    json={"detail": "Invalid JSON"},
                )

            # Match the banking API's generated positive request.
            # Negative tests omit required fields or use invalid types.
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

    transport = httpx.MockTransport(handler)

    with HTTPTestExecutor(
        base_url="https://banking.test",
        transport=transport,
        allow_state_changes=True,
    ) as executor:
        results = [executor.execute(test_case) for test_case in test_cases]

    summary = ExecutionReporter().summarize(results)

    assert summary.total == 7
    assert summary.passed == 3
    assert summary.failed == 0
    assert summary.unasserted == 4
    assert summary.errors == 0

    json_path = tmp_path / "execution-report.json"
    html_path = tmp_path / "execution-report.html"

    JSONReportExporter().export(results, json_path)
    HTMLReportExporter().export(results, html_path)

    assert json_path.exists()
    assert html_path.exists()

    json_data = json.loads(json_path.read_text(encoding="utf-8"))
    html_data = html_path.read_text(encoding="utf-8")

    assert json_data["summary"]["total"] == 7
    assert json_data["summary"]["passed"] == 3
    assert json_data["summary"]["unasserted"] == 4
    assert len(json_data["results"]) == 7

    assert "TestForge Execution Report" in html_data
    assert "42.86%" in html_data

    for result in results:
        assert result.test_id in html_data
