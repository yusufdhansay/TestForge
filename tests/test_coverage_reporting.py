import json

import httpx
import pytest

from testforge.cli import main
from testforge.coverage import ContractCoverageAnalyzer
from testforge.execution_models import ExecutionResult, ExecutionStatus
from testforge.html_reporter import HTMLReportExporter
from testforge.json_reporter import JSONReportExporter
from testforge.models import (
    APISpecification,
    GeneratedTestCase,
    TestCategory,
)


def make_coverage():
    specification = APISpecification.model_validate(
        {
            "openapi_version": "3.0.3",
            "title": "Coverage Reporting API",
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
            ],
        }
    )

    test_cases = [
        GeneratedTestCase(
            test_id="TC-0001",
            name="GET /users",
            category=TestCategory.POSITIVE,
            method="GET",
            path="/users",
            expected_status_codes=[200],
        ),
        GeneratedTestCase(
            test_id="TC-0002",
            name="POST /users",
            category=TestCategory.POSITIVE,
            method="POST",
            path="/users",
            expected_status_codes=[201],
        ),
    ]

    results = [
        ExecutionResult(
            test_id="TC-0001",
            status=ExecutionStatus.PASSED,
            actual_status_code=200,
            expected_status_codes=[200],
            response_time_ms=12.5,
        ),
        ExecutionResult(
            test_id="TC-0002",
            status=ExecutionStatus.ERROR,
            actual_status_code=None,
            expected_status_codes=[201],
            error_message="State-changing requests are disabled",
        ),
    ]

    coverage = ContractCoverageAnalyzer().analyze(
        specification,
        test_cases,
        results,
    )

    return results, coverage


def test_json_report_includes_coverage():
    results, coverage = make_coverage()

    report = JSONReportExporter().build_report(
        results,
        coverage=coverage,
    )

    assert set(report) == {"summary", "results", "coverage"}
    assert report["summary"]["total"] == 2
    assert len(report["results"]) == 2

    assert report["coverage"]["total_operations"] == 2
    assert report["coverage"]["generated_operations"] == 2
    assert report["coverage"]["executed_operations"] == 1
    assert report["coverage"]["generated_coverage_percent"] == 100.0
    assert report["coverage"]["executed_coverage_percent"] == 50.0
    assert report["coverage"]["untested_operations"] == ["POST /users"]


def test_json_report_without_coverage_remains_compatible():
    results, _ = make_coverage()

    report = JSONReportExporter().build_report(results)

    assert set(report) == {"summary", "results"}


def test_json_export_writes_coverage(tmp_path):
    results, coverage = make_coverage()
    output = tmp_path / "coverage.json"

    JSONReportExporter().export(
        results,
        output,
        coverage=coverage,
    )

    report = json.loads(output.read_text(encoding="utf-8"))

    assert report["coverage"]["executed_coverage_percent"] == 50.0
    assert report["coverage"]["methods"][0]["method"] == "GET"


def test_html_report_includes_coverage():
    results, coverage = make_coverage()

    html = HTMLReportExporter().build_report(
        results,
        coverage=coverage,
    )

    assert "Contract Coverage" in html
    assert "Coverage by HTTP Method" in html
    assert "Untested API Operations" in html
    assert "Generated Coverage" in html
    assert "Executed Coverage" in html
    assert "50.00%" in html
    assert "POST /users" in html
    assert "Individual Test Results" in html
    assert "Response Time Statistics" in html


def test_html_report_without_coverage_remains_compatible():
    results, _ = make_coverage()

    html = HTMLReportExporter().build_report(results)

    assert "Individual Test Results" in html
    assert "Response Time Statistics" in html
    assert "Contract Coverage" not in html


def test_html_report_escapes_untested_operation():
    results, coverage = make_coverage()

    coverage.untested_operations = ["GET /search/<script>alert(1)</script>"]

    html = HTMLReportExporter().build_report(
        results,
        coverage=coverage,
    )

    assert "&lt;script&gt;" in html
    assert "<script>alert(1)</script>" not in html


def test_html_export_writes_coverage(tmp_path):
    results, coverage = make_coverage()
    output = tmp_path / "coverage.html"

    HTMLReportExporter().export(
        results,
        output,
        coverage=coverage,
    )

    html = output.read_text(encoding="utf-8")

    assert html.startswith("<!DOCTYPE html>")
    assert "Contract Coverage" in html
    assert "POST /users" in html


@pytest.mark.parametrize("report_format", ["json", "html"])
def test_cli_includes_contract_coverage(
    tmp_path,
    monkeypatch,
    capsys,
    report_format,
):
    specification = {
        "openapi": "3.0.3",
        "info": {
            "title": "CLI Coverage API",
            "version": "1.0.0",
        },
        "paths": {
            "/users": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "OK",
                        }
                    }
                },
                "post": {
                    "responses": {
                        "201": {
                            "description": "Created",
                        }
                    }
                },
            }
        },
    }

    spec_path = tmp_path / "openapi.json"
    spec_path.write_text(
        json.dumps(specification),
        encoding="utf-8",
    )

    output_path = tmp_path / f"report.{report_format}"

    def handler(request):
        return httpx.Response(
            200,
            json={"message": "ok"},
        )

    def mock_executor_init(
        self,
        base_url,
        allow_network=False,
        approved_origins=None,
        allow_state_changes=False,
    ):
        self.base_url = base_url
        self.allow_network = allow_network
        self.approved_origins = approved_origins or set()
        self.allow_state_changes = allow_state_changes
        self.client = httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url=base_url,
        )

    monkeypatch.setattr(
        "testforge.cli.HTTPTestExecutor.__init__",
        mock_executor_init,
    )

    exit_code = main(
        [
            "run",
            str(spec_path),
            "--base-url",
            "https://api.example.com",
            "--allow-network",
            "--report",
            report_format,
            "--output",
            str(output_path),
        ]
    )

    output = capsys.readouterr().out

    # GET receives an HTTP response; POST is blocked by default.
    assert exit_code == 1
    assert "Contract Coverage" in output
    assert "Total operations:       2" in output
    assert "Generated coverage:     100.00%" in output
    assert "Executed coverage:      50.00%" in output
    assert "POST /users" in output

    assert output_path.exists()

    if report_format == "json":
        report = json.loads(output_path.read_text(encoding="utf-8"))
        assert report["coverage"]["total_operations"] == 2
        assert report["coverage"]["executed_operations"] == 1
        assert report["coverage"]["untested_operations"] == ["POST /users"]
    else:
        html = output_path.read_text(encoding="utf-8")
        assert "Contract Coverage" in html
        assert "50.00%" in html
        assert "POST /users" in html
