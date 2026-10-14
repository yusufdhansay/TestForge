"""Phase 10E.2: opt-in negative authentication HTTP integration tests."""

import json

import httpx
import pytest

from testforge.auth_execution import build_auth_test_cases
from testforge.auth_generator import generate_auth_scenarios
from testforge.cli import main
from testforge.executor import HTTPTestExecutor
from testforge.models import GeneratedTestCase, TestCategory
from testforge.security import analyze_security
from testforge.security_routing import build_operation_auth


@pytest.fixture(autouse=True)
def clear_auth_environment(monkeypatch):
    for name in (
        "TESTFORGE_BEARER_TOKEN",
        "TESTFORGE_API_KEY",
        "TESTFORGE_BASIC_USERNAME",
        "TESTFORGE_BASIC_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)


def document(scheme="bearer", *, location="header"):
    if scheme == "bearer":
        definition = {"type": "http", "scheme": "bearer"}
    elif scheme == "basic":
        definition = {"type": "http", "scheme": "basic"}
    else:
        definition = {
            "type": "apiKey",
            "in": location,
            "name": "X-API-Key" if location == "header" else "api_key",
        }
    return {
        "openapi": "3.0.3",
        "info": {"title": "Auth execution", "version": "1"},
        "components": {"securitySchemes": {"Auth": definition}},
        "security": [{"Auth": []}],
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


def install_transport(monkeypatch, captured, *, reject_invalid=True):
    original_init = HTTPTestExecutor.__init__

    def handler(request):
        captured.append(request)
        authorized = (
            request.headers.get("authorization")
            in {"Bearer real-secret", "Basic cmVhbDpzZWNyZXQ="}
            or request.headers.get("x-api-key") == "real-secret"
            or request.url.params.get("api_key") == "real-secret"
        )
        return httpx.Response(200 if authorized or not reject_invalid else 401)

    def mocked_init(self, base_url, **kwargs):
        return original_init(
            self, base_url, transport=httpx.MockTransport(handler), **kwargs
        )

    monkeypatch.setattr(HTTPTestExecutor, "__init__", mocked_init)


def run_cli(tmp_path, spec, *args):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return main(
        [
            "run",
            str(path),
            "--base-url",
            "https://example.test",
            "--allow-network",
            "--output",
            str(tmp_path / "report.json"),
            *args,
        ]
    )


def test_bearer_opt_in_sends_three_negative_requests(tmp_path, monkeypatch):
    captured = []
    install_transport(monkeypatch, captured)
    code = run_cli(tmp_path, document(), "--bearer-token", "real-secret", "--test-auth")
    assert code == 0
    assert len(captured) == 4
    assert captured[0].headers["authorization"] == "Bearer real-secret"
    assert "authorization" not in captured[1].headers
    assert captured[2].headers["authorization"] == "Bearer testforge-invalid-credential"
    assert captured[3].headers["authorization"] == "Bearer"
    assert all("real-secret" not in str(request.url) for request in captured)


def test_opt_out_preserves_existing_request_count(tmp_path, monkeypatch):
    captured = []
    install_transport(monkeypatch, captured)
    code = run_cli(tmp_path, document(), "--bearer-token", "real-secret")
    assert code == 0
    assert len(captured) == 1


def test_basic_auth_mutations_do_not_reuse_password(tmp_path, monkeypatch):
    captured = []
    install_transport(monkeypatch, captured)
    code = run_cli(
        tmp_path,
        document("basic"),
        "--basic-username",
        "real",
        "--basic-password",
        "secret",
        "--test-auth",
    )
    assert code == 0
    assert len(captured) == 4
    assert captured[0].headers["authorization"] == "Basic cmVhbDpzZWNyZXQ="
    assert "authorization" not in captured[1].headers
    assert captured[2].headers["authorization"] == "Basic dGVzdGZvcmdlOmludmFsaWQ="
    assert captured[3].headers["authorization"] == "Basic !!!"


@pytest.mark.parametrize("location", ["header", "query"])
def test_api_key_mutations_are_isolated(tmp_path, monkeypatch, location):
    captured = []
    install_transport(monkeypatch, captured)
    args = ["--api-key", "real-secret", "--api-key-in", location]
    args += ["--api-key-name", "X-API-Key" if location == "header" else "api_key"]
    code = run_cli(
        tmp_path, document("apiKey", location=location), *args, "--test-auth"
    )
    assert code == 0
    assert len(captured) == 3
    if location == "header":
        assert "x-api-key" not in captured[1].headers
        assert captured[2].headers["x-api-key"] == "testforge-invalid-credential"
    else:
        assert "api_key" not in captured[1].url.params
        assert captured[2].url.params["api_key"] == "testforge-invalid-credential"


def test_auth_failure_causes_nonzero_exit(tmp_path, monkeypatch):
    captured = []
    install_transport(monkeypatch, captured, reject_invalid=False)
    code = run_cli(tmp_path, document(), "--bearer-token", "real-secret", "--test-auth")
    assert code == 1
    assert len(captured) == 4


def test_public_operations_do_not_generate_auth_tests():
    spec = document()
    spec["paths"]["/users"]["get"]["security"] = []
    analysis = analyze_security(spec)
    routing = build_operation_auth(analysis, bearer_token="real-secret")
    assert generate_auth_scenarios(analysis, routing) == []


def test_generated_negative_cases_do_not_include_real_credentials():
    spec = document()
    analysis = analyze_security(spec)
    routing = build_operation_auth(analysis, bearer_token="real-secret")
    scenarios = generate_auth_scenarios(analysis, routing)
    base = GeneratedTestCase(
        test_id="TC-0001",
        name="positive",
        category=TestCategory.POSITIVE,
        method="GET",
        path="/users",
        headers={"Authorization": "Bearer real-secret"},
        expected_status_codes=[200],
    )
    cases = build_auth_test_cases(scenarios, [base], analysis)
    assert len(cases) == 3
    assert all("real-secret" not in str(case.model_dump()) for case in cases)
    assert all(case.expected_status_codes == [401] for case in cases)
