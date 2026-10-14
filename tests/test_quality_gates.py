import json

import httpx
import pytest

from testforge.cli import build_parser, main
from testforge.executor import HTTPTestExecutor


def make_specification(tmp_path, include_post=False):
    """Create a small OpenAPI specification for quality-gate tests."""
    paths = {
        "/health": {
            "get": {
                "responses": {
                    "200": {"description": "Healthy"},
                }
            }
        }
    }

    if include_post:
        paths["/transactions"] = {
            "post": {
                "responses": {
                    "201": {"description": "Created"},
                }
            }
        }

    spec_path = tmp_path / "api.json"
    spec_path.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "info": {
                    "title": "Quality Gate API",
                    "version": "1.0.0",
                },
                "paths": paths,
            }
        ),
        encoding="utf-8",
    )

    return spec_path


def install_mock_http(monkeypatch):
    """Use mocked HTTP responses without accessing the network."""
    original_init = HTTPTestExecutor.__init__

    def mocked_init(self, base_url, **kwargs):
        def handler(request):
            if request.method == "POST":
                return httpx.Response(201)

            return httpx.Response(200)

        return original_init(
            self,
            base_url,
            transport=httpx.MockTransport(handler),
            **kwargs,
        )

    monkeypatch.setattr(HTTPTestExecutor, "__init__", mocked_init)


def run_with_gates(
    tmp_path,
    monkeypatch,
    capsys,
    extra_args,
    include_post=False,
):
    spec_path = make_specification(
        tmp_path,
        include_post=include_post,
    )
    install_mock_http(monkeypatch)

    report_path = tmp_path / "report.json"

    exit_code = main(
        [
            "run",
            str(spec_path),
            "--base-url",
            "https://mock.test",
            "--allow-network",
            "--output",
            str(report_path),
            *extra_args,
        ]
    )

    captured = capsys.readouterr()
    report = json.loads(report_path.read_text(encoding="utf-8"))

    return exit_code, captured, report


def test_quality_gate_defaults_to_none():
    args = build_parser().parse_args(
        [
            "run",
            "api.json",
            "--base-url",
            "https://mock.test",
        ]
    )

    assert args.min_generated_coverage is None
    assert args.min_executed_coverage is None


@pytest.mark.parametrize("value", ["0", "25", "80.5", "100"])
def test_quality_gate_accepts_valid_percentages(value):
    args = build_parser().parse_args(
        [
            "run",
            "api.json",
            "--base-url",
            "https://mock.test",
            "--min-executed-coverage",
            value,
        ]
    )

    assert args.min_executed_coverage == float(value)


@pytest.mark.parametrize(
    "value",
    ["-1", "100.1", "abc", "nan", "inf", "-inf"],
)
@pytest.mark.parametrize(
    "flag",
    [
        "--min-generated-coverage",
        "--min-executed-coverage",
    ],
)
def test_quality_gate_rejects_invalid_percentages(flag, value):
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(
            [
                "run",
                "api.json",
                "--base-url",
                "https://mock.test",
                flag,
                value,
            ]
        )

    assert error.value.code == 2


def test_generated_coverage_gate_passes(
    tmp_path,
    monkeypatch,
    capsys,
):
    exit_code, captured, report = run_with_gates(
        tmp_path,
        monkeypatch,
        capsys,
        ["--min-generated-coverage", "100"],
    )

    assert exit_code == 0
    assert "CI Quality Gates: PASSED" in captured.out
    assert report["coverage"]["generated_coverage_percent"] == 100.0


def test_executed_coverage_gate_passes(
    tmp_path,
    monkeypatch,
    capsys,
):
    exit_code, captured, report = run_with_gates(
        tmp_path,
        monkeypatch,
        capsys,
        ["--min-executed-coverage", "100"],
    )

    assert exit_code == 0
    assert "CI Quality Gates: PASSED" in captured.out
    assert report["coverage"]["executed_coverage_percent"] == 100.0


def test_executed_coverage_gate_fails_for_blocked_post(
    tmp_path,
    monkeypatch,
    capsys,
):
    exit_code, captured, report = run_with_gates(
        tmp_path,
        monkeypatch,
        capsys,
        ["--min-executed-coverage", "80"],
        include_post=True,
    )

    assert exit_code == 1
    assert "CI Quality Gates: FAILED" in captured.err
    assert "Executed coverage 50.00%" in captured.err
    assert "80.00%" in captured.err
    assert report["coverage"]["executed_coverage_percent"] == 50.0
    assert report["coverage"]["generated_coverage_percent"] == 100.0


def test_zero_threshold_passes_even_with_blocked_post(
    tmp_path,
    monkeypatch,
    capsys,
):
    exit_code, captured, report = run_with_gates(
        tmp_path,
        monkeypatch,
        capsys,
        ["--min-executed-coverage", "0"],
        include_post=True,
    )

    # The quality gate passes, but the blocked POST still
    # produces an execution error and a nonzero exit code.
    assert exit_code == 1
    assert "CI Quality Gates: PASSED" in captured.out
    assert report["coverage"]["executed_coverage_percent"] == 50.0
    assert report["summary"]["errors"] >= 1


def test_both_quality_gates_pass(
    tmp_path,
    monkeypatch,
    capsys,
):
    exit_code, captured, report = run_with_gates(
        tmp_path,
        monkeypatch,
        capsys,
        [
            "--min-generated-coverage",
            "100",
            "--min-executed-coverage",
            "100",
        ],
    )

    assert exit_code == 0
    assert "CI Quality Gates: PASSED" in captured.out
    assert report["coverage"]["generated_coverage_percent"] == 100.0
    assert report["coverage"]["executed_coverage_percent"] == 100.0


def test_gate_failure_does_not_prevent_report_export(
    tmp_path,
    monkeypatch,
    capsys,
):
    exit_code, captured, report = run_with_gates(
        tmp_path,
        monkeypatch,
        capsys,
        ["--min-executed-coverage", "90"],
        include_post=True,
    )

    assert exit_code == 1
    assert "CI Quality Gates: FAILED" in captured.err
    assert report["summary"]["total"] >= 2
    assert report["coverage"]["total_operations"] == 2


def test_no_quality_gates_preserves_existing_behavior(
    tmp_path,
    monkeypatch,
    capsys,
):
    exit_code, captured, report = run_with_gates(
        tmp_path,
        monkeypatch,
        capsys,
        [],
    )

    assert exit_code == 0
    assert "CI Quality Gates" not in captured.out
    assert "CI Quality Gates" not in captured.err
    assert report["summary"]["failed"] == 0
    assert report["summary"]["errors"] == 0
