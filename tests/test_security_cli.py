"""End-to-end CLI tests for OpenAPI security-aware execution."""

import json

import httpx
import pytest

from testforge.cli import main
from testforge.executor import HTTPTestExecutor


@pytest.fixture(autouse=True)
def clear_auth_environment(monkeypatch):
    """Prevent local credentials from affecting tests."""
    for name in (
        "TESTFORGE_BEARER_TOKEN",
        "TESTFORGE_API_KEY",
        "TESTFORGE_BASIC_USERNAME",
        "TESTFORGE_BASIC_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)


def make_spec(tmp_path, *, security=None, schemes=None, paths=None):
    """Write a minimal OpenAPI specification."""
    document = {
        "openapi": "3.0.3",
        "info": {"title": "Security CLI Test", "version": "1.0"},
        "components": {
            "securitySchemes": schemes
            or {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                },
                "ApiKey": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                },
            }
        },
        "paths": paths
        or {
            "/users": {
                "get": {
                    "responses": {
                        "200": {"description": "OK"},
                    }
                }
            }
        },
    }

    if security is not None:
        document["security"] = security

    path = tmp_path / "spec.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def install_mock_transport(monkeypatch, captured):
    """Intercept HTTP requests without accessing the network."""
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

    monkeypatch.setattr(HTTPTestExecutor, "__init__", mocked_init)


def run_cli(spec, tmp_path, *options):
    return main(
        [
            "run",
            str(spec),
            "--base-url",
            "https://example.test",
            "--allow-network",
            "--output",
            str(tmp_path / "report.json"),
            *options,
        ]
    )


def test_missing_bearer_credentials_block_all_requests(tmp_path, monkeypatch, capsys):
    spec = make_spec(
        tmp_path,
        security=[{"BearerAuth": []}],
    )

    captured = []
    install_mock_transport(monkeypatch, captured)

    exit_code = run_cli(spec, tmp_path)

    assert exit_code == 2
    assert captured == []
    assert "security requirements are not satisfied" in capsys.readouterr().err


def test_wrong_authentication_type_is_rejected(tmp_path, monkeypatch):
    spec = make_spec(
        tmp_path,
        security=[{"BearerAuth": []}],
    )

    captured = []
    install_mock_transport(monkeypatch, captured)

    exit_code = run_cli(
        spec,
        tmp_path,
        "--basic-username",
        "admin",
        "--basic-password",
        "password",
    )

    assert exit_code == 2
    assert captured == []


def test_public_and_protected_operations_route_credentials(tmp_path, monkeypatch):
    spec = make_spec(
        tmp_path,
        security=[{"BearerAuth": []}],
        paths={
            "/health": {
                "get": {
                    "security": [],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/users": {
                "get": {
                    "responses": {"200": {"description": "OK"}},
                }
            },
        },
    )

    captured = []
    install_mock_transport(monkeypatch, captured)

    exit_code = run_cli(
        spec,
        tmp_path,
        "--bearer-token",
        "test-secret-token",
    )

    assert exit_code == 0
    assert len(captured) == 2

    requests_by_path = {request.url.path: request for request in captured}

    assert "authorization" not in requests_by_path["/health"].headers
    assert (
        requests_by_path["/users"].headers["authorization"]
        == "Bearer test-secret-token"
    )


def test_operation_override_uses_api_key_instead_of_bearer(tmp_path, monkeypatch):
    spec = make_spec(
        tmp_path,
        security=[{"BearerAuth": []}],
        paths={
            "/users": {
                "get": {
                    "security": [{"ApiKey": []}],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    )

    captured = []
    install_mock_transport(monkeypatch, captured)

    exit_code = run_cli(
        spec,
        tmp_path,
        "--api-key",
        "test-api-key",
        "--api-key-name",
        "X-API-Key",
    )

    assert exit_code == 0
    assert len(captured) == 1
    assert captured[0].headers["x-api-key"] == "test-api-key"
    assert "authorization" not in captured[0].headers


def test_or_alternative_accepts_available_api_key(tmp_path, monkeypatch):
    spec = make_spec(
        tmp_path,
        security=[
            {"BearerAuth": []},
            {"ApiKey": []},
        ],
    )

    captured = []
    install_mock_transport(monkeypatch, captured)

    exit_code = run_cli(
        spec,
        tmp_path,
        "--api-key",
        "test-api-key",
        "--api-key-name",
        "X-API-Key",
    )

    assert exit_code == 0
    assert len(captured) == 1
    assert captured[0].headers["x-api-key"] == "test-api-key"


def test_and_requirement_sends_both_credentials(tmp_path, monkeypatch):
    spec = make_spec(
        tmp_path,
        security=[
            {
                "BearerAuth": [],
                "ApiKey": [],
            }
        ],
    )

    captured = []
    install_mock_transport(monkeypatch, captured)

    exit_code = run_cli(
        spec,
        tmp_path,
        "--bearer-token",
        "test-token",
        "--api-key",
        "test-key",
        "--api-key-name",
        "X-API-Key",
    )

    assert exit_code == 0
    assert len(captured) == 1
    assert captured[0].headers["authorization"] == "Bearer test-token"
    assert captured[0].headers["x-api-key"] == "test-key"


def test_unsupported_security_blocks_execution(tmp_path, monkeypatch):
    spec = make_spec(
        tmp_path,
        security=[{"OAuth": []}],
        schemes={
            "OAuth": {
                "type": "oauth2",
                "flows": {},
            }
        },
    )

    captured = []
    install_mock_transport(monkeypatch, captured)

    exit_code = run_cli(
        spec,
        tmp_path,
        "--bearer-token",
        "test-token",
    )

    assert exit_code == 2
    assert captured == []


def test_error_does_not_disclose_credentials(tmp_path, monkeypatch, capsys):
    spec = make_spec(
        tmp_path,
        security=[{"ApiKey": []}],
    )

    captured = []
    install_mock_transport(monkeypatch, captured)

    secret = "super-secret-credential"

    exit_code = run_cli(
        spec,
        tmp_path,
        "--api-key",
        secret,
        "--api-key-name",
        "Wrong-Header",
    )

    output = capsys.readouterr()

    assert exit_code == 2
    assert captured == []
    assert secret not in output.out
    assert secret not in output.err
