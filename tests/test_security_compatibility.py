"""Regression tests for OpenAPI authentication compatibility."""

import json

import httpx
import pytest

from testforge.cli import main
from testforge.executor import HTTPTestExecutor


@pytest.fixture(autouse=True)
def clear_auth_environment(monkeypatch):
    """Keep external credentials from affecting the tests."""
    for name in (
        "TESTFORGE_BEARER_TOKEN",
        "TESTFORGE_API_KEY",
        "TESTFORGE_BASIC_USERNAME",
        "TESTFORGE_BASIC_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)


def execute_spec(tmp_path, monkeypatch, document, *options):
    """Execute a specification using an in-memory HTTP transport."""
    spec_path = tmp_path / "spec.json"
    report_path = tmp_path / "report.json"

    spec_path.write_text(
        json.dumps(document),
        encoding="utf-8",
    )

    captured = []
    original_init = HTTPTestExecutor.__init__

    def handler(request):
        captured.append(request)
        return httpx.Response(200)

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

    exit_code = main(
        [
            "run",
            str(spec_path),
            "--base-url",
            "https://example.test",
            "--allow-network",
            "--output",
            str(report_path),
            *options,
        ]
    )

    return exit_code, captured


def make_spec(
    *,
    schemes=None,
    global_security="absent",
    operation_security="absent",
):
    """Create an OpenAPI specification with configurable security."""
    operation = {
        "responses": {
            "200": {"description": "OK"},
        }
    }

    if operation_security != "absent":
        operation["security"] = operation_security

    document = {
        "openapi": "3.0.3",
        "info": {
            "title": "Compatibility Test",
            "version": "1.0",
        },
        "paths": {
            "/users": {
                "get": operation,
            }
        },
    }

    if schemes is not None:
        document["components"] = {
            "securitySchemes": schemes,
        }

    if global_security != "absent":
        document["security"] = global_security

    return document


BEARER_SCHEME = {
    "BearerAuth": {
        "type": "http",
        "scheme": "bearer",
    }
}


def test_no_security_declarations_preserves_legacy_bearer(tmp_path, monkeypatch):
    document = make_spec()

    exit_code, requests = execute_spec(
        tmp_path,
        monkeypatch,
        document,
        "--bearer-token",
        "legacy-token",
    )

    assert exit_code == 0
    assert len(requests) == 1
    assert requests[0].headers["authorization"] == "Bearer legacy-token"


def test_unused_security_scheme_preserves_legacy_bearer(tmp_path, monkeypatch):
    document = make_spec(schemes=BEARER_SCHEME)

    exit_code, requests = execute_spec(
        tmp_path,
        monkeypatch,
        document,
        "--bearer-token",
        "legacy-token",
    )

    assert exit_code == 0
    assert len(requests) == 1
    assert requests[0].headers["authorization"] == "Bearer legacy-token"


def test_explicit_global_public_security_suppresses_bearer(tmp_path, monkeypatch):
    document = make_spec(
        schemes=BEARER_SCHEME,
        global_security=[],
    )

    exit_code, requests = execute_spec(
        tmp_path,
        monkeypatch,
        document,
        "--bearer-token",
        "secret-token",
    )

    assert exit_code == 0
    assert len(requests) == 1
    assert "authorization" not in requests[0].headers


def test_explicit_operation_public_security_suppresses_bearer(tmp_path, monkeypatch):
    document = make_spec(
        schemes=BEARER_SCHEME,
        operation_security=[],
    )

    exit_code, requests = execute_spec(
        tmp_path,
        monkeypatch,
        document,
        "--bearer-token",
        "secret-token",
    )

    assert exit_code == 0
    assert len(requests) == 1
    assert "authorization" not in requests[0].headers


def test_explicit_protected_security_uses_bearer(tmp_path, monkeypatch):
    document = make_spec(
        schemes=BEARER_SCHEME,
        global_security=[{"BearerAuth": []}],
    )

    exit_code, requests = execute_spec(
        tmp_path,
        monkeypatch,
        document,
        "--bearer-token",
        "protected-token",
    )

    assert exit_code == 0
    assert len(requests) == 1
    assert requests[0].headers["authorization"] == "Bearer protected-token"


def test_malformed_security_returns_clean_cli_error(tmp_path, monkeypatch, capsys):
    document = make_spec(
        schemes=BEARER_SCHEME,
        global_security="invalid-security-value",
    )

    exit_code, requests = execute_spec(
        tmp_path,
        monkeypatch,
        document,
    )

    output = capsys.readouterr()

    assert exit_code == 2
    assert requests == []
    assert "security requirements must be a list" in output.err
