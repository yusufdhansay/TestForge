import json

import pytest

from testforge.execution_models import ExecutionResult, ExecutionStatus
from testforge.json_reporter import JSONReportExporter


def sample_results():
    return [
        ExecutionResult(
            test_id="TC-0001",
            status=ExecutionStatus.PASSED,
            actual_status_code=200,
            expected_status_codes=[200],
            response_time_ms=10.0,
        ),
        ExecutionResult(
            test_id="TC-0002",
            status=ExecutionStatus.FAILED,
            actual_status_code=500,
            expected_status_codes=[200],
            response_time_ms=30.0,
        ),
    ]


def test_build_report():
    report = JSONReportExporter().build_report(sample_results())

    assert report["summary"]["total"] == 2
    assert report["summary"]["passed"] == 1
    assert report["summary"]["failed"] == 1
    assert report["summary"]["pass_rate"] == 50.0

    assert len(report["results"]) == 2
    assert report["results"][0]["status"] == "passed"
    assert report["results"][1]["status"] == "failed"


def test_export_json_file(tmp_path):
    output = tmp_path / "report.json"

    returned_path = JSONReportExporter().export(
        sample_results(),
        output,
    )

    assert returned_path == output
    assert output.exists()

    with output.open(encoding="utf-8") as file:
        data = json.load(file)

    assert data["summary"]["total"] == 2
    assert len(data["results"]) == 2
    assert data["results"][0]["test_id"] == "TC-0001"


def test_existing_report_not_overwritten(tmp_path):
    output = tmp_path / "report.json"
    output.write_text("original", encoding="utf-8")

    with pytest.raises(FileExistsError):
        JSONReportExporter().export(sample_results(), output)

    assert output.read_text(encoding="utf-8") == "original"


def test_invalid_file_extension(tmp_path):
    with pytest.raises(ValueError, match="JSON file"):
        JSONReportExporter().export(
            sample_results(),
            tmp_path / "report.txt",
        )


def test_missing_output_directory(tmp_path):
    with pytest.raises(FileNotFoundError):
        JSONReportExporter().export(
            sample_results(),
            tmp_path / "missing" / "report.json",
        )


def test_empty_report(tmp_path):
    output = tmp_path / "empty.json"

    JSONReportExporter().export([], output)

    with output.open(encoding="utf-8") as file:
        data = json.load(file)

    assert data["summary"]["total"] == 0
    assert data["summary"]["pass_rate"] == 0.0
    assert data["results"] == []
