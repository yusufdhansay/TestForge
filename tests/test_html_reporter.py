import pytest

from testforge.execution_models import ExecutionResult, ExecutionStatus
from testforge.html_reporter import HTMLReportExporter


def sample_results():
    return [
        ExecutionResult(
            test_id="TC-0001",
            status=ExecutionStatus.PASSED,
            actual_status_code=200,
            expected_status_codes=[200],
            response_time_ms=12.5,
        ),
        ExecutionResult(
            test_id="TC-0002",
            status=ExecutionStatus.FAILED,
            actual_status_code=500,
            expected_status_codes=[200],
            response_time_ms=30.0,
        ),
    ]


def test_build_html_report():
    html = HTMLReportExporter().build_report(sample_results())

    assert "<!DOCTYPE html>" in html
    assert "TestForge Execution Report" in html
    assert "TC-0001" in html
    assert "TC-0002" in html
    assert "50.00%" in html


def test_html_contains_response_time_statistics():
    html = HTMLReportExporter().build_report(sample_results())

    assert "21.25 ms" in html
    assert "12.50 ms" in html
    assert "30.00 ms" in html


def test_export_html_file(tmp_path):
    output = tmp_path / "report.html"

    returned_path = HTMLReportExporter().export(
        sample_results(),
        output,
    )

    assert returned_path == output
    assert output.exists()
    assert "<html" in output.read_text(encoding="utf-8")


def test_existing_html_report_not_overwritten(tmp_path):
    output = tmp_path / "report.html"
    output.write_text("original", encoding="utf-8")

    with pytest.raises(FileExistsError):
        HTMLReportExporter().export(sample_results(), output)

    assert output.read_text(encoding="utf-8") == "original"


def test_html_escapes_untrusted_content():
    results = [
        ExecutionResult(
            test_id="<script>alert(1)</script>",
            status=ExecutionStatus.ERROR,
            error_message="<img src=x onerror=alert(1)>",
        )
    ]

    html = HTMLReportExporter().build_report(results)

    assert "<script>alert(1)</script>" not in html
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img" in html


def test_empty_html_report():
    html = HTMLReportExporter().build_report([])

    assert "0.00%" in html
    assert "N/A" in html
    assert "Individual Test Results" in html


def test_invalid_html_extension(tmp_path):
    with pytest.raises(ValueError, match="HTML file"):
        HTMLReportExporter().export(
            sample_results(),
            tmp_path / "report.txt",
        )
