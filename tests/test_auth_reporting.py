"""Phase 10E.3 authentication reporting and CI regression tests."""

import json

import httpx
import pytest

from testforge.auth_reporter import (
    evaluate_auth_gate,
    export_auth_report,
    summarize_auth_results,
)
from testforge.cli import main
from testforge.execution_models import ExecutionResult, ExecutionStatus
from testforge.executor import HTTPTestExecutor
from testforge.models import GeneratedTestCase, TestCategory


@pytest.fixture(autouse=True)
def clear_auth_environment(monkeypatch):
    for name in (
        "TESTFORGE_BEARER_TOKEN",
        "TESTFORGE_API_KEY",
        "TESTFORGE_BASIC_USERNAME",
        "TESTFORGE_BASIC_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)


def auth_case(test_id="AUTH-0001"):
    return GeneratedTestCase(
        test_id=test_id,
        name="GET /users - missing bearer",
        category=TestCategory.NEGATIVE,
        method="GET",
        path="/users",
        expected_status_codes=[401],
    )


def auth_result(
    test_id="AUTH-0001",
    status=ExecutionStatus.PASSED,
    actual_status_code=401,
):
    return ExecutionResult(
        test_id=test_id,
        status=status,
        actual_status_code=actual_status_code,
        expected_status_codes=[401],
    )


def make_document():
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Authentication reporting",
            "version": "1.0",
        },
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                }
            }
        },
        "security": [{"BearerAuth": []}],
        "paths": {
            "/users": {
                "get": {
                    "responses": {
                        "200": {"description": "OK"},
                        "401": {"description": "Unauthorized"},
                    }
                }
            }
        },
    }


def run_cli(tmp_path, document, *options):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(document), encoding="utf-8")

    return main(
        [
            "run",
            str(spec_path),
            "--base-url",
            "https://example.test",
            "--allow-network",
            "--output",
            str(tmp_path / "report.json"),
            *options,
        ]
    )


def install_transport(monkeypatch, *, reject_invalid=True):
    original_init = HTTPTestExecutor.__init__

    def handler(request):
        authorized = request.headers.get("authorization") == "Bearer real-secret"

        if authorized or not reject_invalid:
            return httpx.Response(200)

        return httpx.Response(401)

    def mocked_init(self, base_url, **kwargs):
        return original_init(
            self,
            base_url,
            transport=httpx.MockTransport(handler),
            **kwargs,
        )

    monkeypatch.setattr(
        HTTPTestExecutor,
        "__init__",
        mocked_init,
    )


def test_auth_summary_counts_outcomes():
    cases = [
        auth_case("AUTH-0001"),
        auth_case("AUTH-0002"),
        auth_case("AUTH-0003"),
    ]

    results = [
        auth_result("AUTH-0001"),
        auth_result(
            "AUTH-0002",
            ExecutionStatus.FAILED,
            200,
        ),
        auth_result(
            "AUTH-0003",
            ExecutionStatus.ERROR,
            None,
        ),
    ]

    summary = summarize_auth_results(cases, results)

    assert summary.generated == 3
    assert summary.executed == 2
    assert summary.passed == 1
    assert summary.failed == 1
    assert summary.errors == 1
    assert summary.pass_rate == 33.33


def test_auth_gate_passes_at_threshold():
    summary = summarize_auth_results(
        [auth_case()],
        [auth_result()],
    )

    assert evaluate_auth_gate(summary, 100) == []


def test_auth_gate_fails_below_threshold():
    cases = [
        auth_case("AUTH-0001"),
        auth_case("AUTH-0002"),
    ]

    results = [
        auth_result("AUTH-0001"),
        auth_result(
            "AUTH-0002",
            ExecutionStatus.FAILED,
            200,
        ),
    ]

    summary = summarize_auth_results(cases, results)

    failures = evaluate_auth_gate(summary, 100)

    assert len(failures) == 1
    assert "50.00%" in failures[0]


def test_auth_gate_fails_when_no_cases_generated():
    summary = summarize_auth_results([], [])

    failures = evaluate_auth_gate(summary, 100)

    assert len(failures) == 1
    assert "no authentication tests" in failures[0]


def test_auth_report_does_not_export_credentials(tmp_path):
    case = auth_case()
    case.headers["Authorization"] = "Bearer super-secret"

    result = auth_result()
    result.error_message = "super-secret"

    summary = summarize_auth_results([case], [result])

    destination = tmp_path / "auth.json"

    export_auth_report(
        destination,
        [case],
        [result],
        summary,
    )

    contents = destination.read_text(encoding="utf-8")
    payload = json.loads(contents)

    assert "super-secret" not in contents
    assert "Authorization" not in contents
    assert payload["summary"]["passed"] == 1
    assert payload["checks"][0]["actual_status_code"] == 401


def test_cli_exports_auth_report_and_passes_gate(
    tmp_path,
    monkeypatch,
    capsys,
):
    install_transport(monkeypatch)

    auth_path = tmp_path / "auth-report.json"

    code = run_cli(
        tmp_path,
        make_document(),
        "--bearer-token",
        "real-secret",
        "--test-auth",
        "--auth-report",
        str(auth_path),
        "--min-auth-pass-rate",
        "100",
    )

    output = capsys.readouterr()

    assert code == 0
    assert auth_path.exists()

    payload = json.loads(auth_path.read_text(encoding="utf-8"))

    assert payload["report_type"] == "authentication_security"
    assert payload["summary"]["generated"] == 3
    assert payload["summary"]["passed"] == 3
    assert payload["summary"]["pass_rate"] == 100.0
    assert len(payload["checks"]) == 3
    assert "CI Quality Gates: PASSED" in output.out
    assert "real-secret" not in auth_path.read_text()


def test_cli_fails_auth_gate_when_endpoint_accepts_invalid_auth(
    tmp_path,
    monkeypatch,
    capsys,
):
    install_transport(
        monkeypatch,
        reject_invalid=False,
    )

    code = run_cli(
        tmp_path,
        make_document(),
        "--bearer-token",
        "real-secret",
        "--test-auth",
        "--min-auth-pass-rate",
        "100",
    )

    output = capsys.readouterr()

    assert code == 1
    assert "CI Quality Gates: FAILED" in output.err
    assert "Authentication pass rate" in output.err


def test_cli_rejects_auth_gate_without_test_auth(
    tmp_path,
    capsys,
):
    code = run_cli(
        tmp_path,
        make_document(),
        "--min-auth-pass-rate",
        "100",
    )

    assert code == 2
    assert "--min-auth-pass-rate requires --test-auth" in (capsys.readouterr().err)


def test_cli_rejects_auth_report_without_test_auth(
    tmp_path,
    capsys,
):
    code = run_cli(
        tmp_path,
        make_document(),
        "--auth-report",
        str(tmp_path / "auth.json"),
    )

    assert code == 2
    assert "--auth-report requires --test-auth" in (capsys.readouterr().err)


def test_cli_rejects_overlapping_report_destinations(
    tmp_path,
    capsys,
):
    report_path = tmp_path / "report.json"

    code = run_cli(
        tmp_path,
        make_document(),
        "--test-auth",
        "--auth-report",
        str(report_path),
    )

    assert code == 2
    assert "separate output path" in capsys.readouterr().err
