"""CI regression tests for negative authentication testing."""

import json

import httpx
import pytest

from testforge.cli import main
from testforge.executor import HTTPTestExecutor


@pytest.fixture(autouse=True)
def clear_auth_environment(monkeypatch):
    """Ensure external credentials cannot affect regression tests."""
    for name in (
        "TESTFORGE_BEARER_TOKEN",
        "TESTFORGE_API_KEY",
        "TESTFORGE_BASIC_USERNAME",
        "TESTFORGE_BASIC_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def openapi_spec(tmp_path):
    """Create a minimal protected OpenAPI endpoint."""
    document = {
        "openapi": "3.0.3",
        "info": {
            "title": "TestForge Security CI",
            "version": "1.0.0",
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
            "/protected": {
                "get": {
                    "responses": {
                        "200": {"description": "Success"},
                        "401": {"description": "Unauthorized"},
                    }
                }
            }
        },
    }

    path = tmp_path / "openapi.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def install_transport(monkeypatch, requests, *, reject_invalid=True):
    """Intercept HTTP requests without network access."""
    original_init = HTTPTestExecutor.__init__

    def handler(request):
        requests.append(request)

        valid = request.headers.get("authorization") == "Bearer ci-valid-token"

        if valid or not reject_invalid:
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


def run_cli(spec, tmp_path, *options):
    """Execute TestForge with isolated output paths."""
    return main(
        [
            "run",
            str(spec),
            "--base-url",
            "https://example.test",
            "--allow-network",
            "--output",
            str(tmp_path / "contract-report.json"),
            *options,
        ]
    )


def test_ci_auth_gate_passes_for_protected_endpoint(
    openapi_spec,
    tmp_path,
    monkeypatch,
):
    """Correctly rejected authentication attempts satisfy the gate."""
    requests = []
    install_transport(monkeypatch, requests)

    code = run_cli(
        openapi_spec,
        tmp_path,
        "--bearer-token",
        "ci-valid-token",
        "--test-auth",
        "--min-auth-pass-rate",
        "100",
        "--auth-report",
        str(tmp_path / "auth-report.json"),
    )

    assert code == 0

    report = json.loads((tmp_path / "auth-report.json").read_text(encoding="utf-8"))

    assert report["summary"]["generated"] > 0
    assert report["summary"]["failed"] == 0
    assert report["summary"]["errors"] == 0
    assert report["summary"]["pass_rate"] == 100.0

    assert requests


def test_ci_fails_when_invalid_authentication_is_accepted(
    openapi_spec,
    tmp_path,
    monkeypatch,
    capsys,
):
    """An endpoint accepting invalid credentials must fail CI."""
    requests = []

    install_transport(
        monkeypatch,
        requests,
        reject_invalid=False,
    )

    code = run_cli(
        openapi_spec,
        tmp_path,
        "--bearer-token",
        "ci-valid-token",
        "--test-auth",
        "--min-auth-pass-rate",
        "100",
    )

    output = capsys.readouterr()

    assert code == 1
    assert "CI Quality Gates: FAILED" in output.err
    assert "Authentication pass rate" in output.err


def test_ci_auth_requests_do_not_reuse_real_credentials(
    openapi_spec,
    tmp_path,
    monkeypatch,
):
    """Negative authentication requests must not reuse valid tokens."""
    requests = []
    install_transport(monkeypatch, requests)

    code = run_cli(
        openapi_spec,
        tmp_path,
        "--bearer-token",
        "ci-valid-token",
        "--test-auth",
        "--min-auth-pass-rate",
        "100",
    )

    assert code == 0

    valid_requests = [
        request
        for request in requests
        if request.headers.get("authorization") == "Bearer ci-valid-token"
    ]

    negative_requests = [
        request
        for request in requests
        if request.headers.get("authorization") != "Bearer ci-valid-token"
    ]

    assert len(valid_requests) == 1
    assert negative_requests

    for request in negative_requests:
        assert "ci-valid-token" not in str(request.url)
        assert "ci-valid-token" not in str(dict(request.headers))


def test_ci_auth_report_does_not_expose_credentials(
    openapi_spec,
    tmp_path,
    monkeypatch,
):
    """Authentication security reports must not contain valid secrets."""
    requests = []
    install_transport(monkeypatch, requests)

    code = run_cli(
        openapi_spec,
        tmp_path,
        "--bearer-token",
        "ci-valid-token",
        "--test-auth",
        "--auth-report",
        str(tmp_path / "auth-report.json"),
    )

    assert code == 0

    report_text = (tmp_path / "auth-report.json").read_text(encoding="utf-8")

    assert "ci-valid-token" not in report_text
    assert "Bearer ci-valid-token" not in report_text

    report = json.loads(report_text)

    assert report["report_type"] == "authentication_security"
    assert report["checks"]


def test_ci_rejects_auth_gate_without_auth_testing(
    openapi_spec,
    tmp_path,
    capsys,
):
    """CI must not silently ignore a requested authentication gate."""
    code = run_cli(
        openapi_spec,
        tmp_path,
        "--min-auth-pass-rate",
        "100",
    )

    output = capsys.readouterr()

    assert code == 2
    assert "--min-auth-pass-rate requires --test-auth" in output.err


def test_ci_default_run_does_not_generate_auth_tests(
    openapi_spec,
    tmp_path,
    monkeypatch,
    capsys,
):
    """Ordinary contract execution must remain unchanged."""
    requests = []
    install_transport(monkeypatch, requests)

    code = run_cli(
        openapi_spec,
        tmp_path,
        "--bearer-token",
        "ci-valid-token",
    )

    output = capsys.readouterr()

    assert code == 0
    assert len(requests) == 1
    assert "Authentication Security" not in output.out
    assert not (tmp_path / "auth-report.json").exists()
