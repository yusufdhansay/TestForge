import base64
import json

import httpx
import pytest

from testforge.cli import build_parser, main
from testforge.execution_models import ExecutionStatus
from testforge.executor import (
    HTTPTestExecutor,
    encode_basic_auth,
    validate_basic_auth,
)
from testforge.models import GeneratedTestCase, TestCategory


def make_case(headers=None):
    return GeneratedTestCase(
        test_id="BASIC-001",
        name="Basic authentication request",
        category=TestCategory.POSITIVE,
        method="GET",
        path="/health",
        expected_status_codes=[200],
        headers=headers or {},
    )


def test_basic_auth_header_is_sent():
    def handler(request):
        assert request.headers["Authorization"] == "Basic dXNlcjpwYXNz"
        return httpx.Response(200)

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        basic_username="user",
        basic_password="pass",
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.PASSED


def test_basic_auth_supports_utf8():
    username = "josé"
    password = "pässword"

    expected = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode(
        "ascii"
    )

    assert encode_basic_auth(username, password) == expected


def test_basic_auth_allows_empty_password():
    assert encode_basic_auth("user", "") == "Basic dXNlcjo="


def test_basic_auth_overrides_generated_authorization():
    case = make_case(headers={"authorization": "Bearer old-token"})

    def handler(request):
        assert request.headers["Authorization"] == "Basic dXNlcjpwYXNz"
        return httpx.Response(200)

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        basic_username="user",
        basic_password="pass",
    ) as executor:
        result = executor.execute(case)

    assert result.status == ExecutionStatus.PASSED
    assert case.headers["authorization"] == "Bearer old-token"


def test_basic_and_bearer_conflict():
    with pytest.raises(ValueError, match="Basic and Bearer"):
        HTTPTestExecutor(
            "https://example.test",
            transport=httpx.MockTransport(lambda request: httpx.Response(200)),
            bearer_token="token",
            basic_username="user",
            basic_password="pass",
        )


def test_basic_and_authorization_api_key_conflict():
    with pytest.raises(ValueError, match="conflict"):
        HTTPTestExecutor(
            "https://example.test",
            transport=httpx.MockTransport(lambda request: httpx.Response(200)),
            api_key="secret",
            api_key_name="Authorization",
            basic_username="user",
            basic_password="pass",
        )


def test_basic_and_regular_api_key_coexist():
    def handler(request):
        assert request.headers["Authorization"] == "Basic dXNlcjpwYXNz"
        assert request.headers["X-API-Key"] == "secret"
        return httpx.Response(200)

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        api_key="secret",
        basic_username="user",
        basic_password="pass",
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.PASSED


@pytest.mark.parametrize(
    ("username", "password"),
    [
        (None, "pass"),
        ("user", None),
        ("", "pass"),
        ("user:name", "pass"),
        ("user\nname", "pass"),
        ("user", "pass\rword"),
        ("user", "pass\x00word"),
        ("user", "pass\ud800"),
    ],
)
def test_invalid_basic_credentials(username, password):
    with pytest.raises(ValueError, match="Basic authentication"):
        validate_basic_auth(username, password)


def test_no_basic_credentials_is_valid():
    assert validate_basic_auth(None, None) == (None, None)


def test_basic_auth_redacts_password_from_transport_error():
    secret = "super-secret-password"

    def handler(request):
        raise httpx.ConnectError(
            f"Connection failed: {secret}",
            request=request,
        )

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        basic_username="user",
        basic_password=secret,
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.ERROR
    assert secret not in result.error_message
    assert "[REDACTED]" in result.error_message


def test_basic_auth_redacts_encoded_authorization():
    def handler(request):
        raise httpx.ConnectError(
            f"Request failed: {request.headers['Authorization']}",
            request=request,
        )

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        basic_username="user",
        basic_password="pass",
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.ERROR
    assert "dXNlcjpwYXNz" not in result.error_message
    assert "[REDACTED]" in result.error_message


def test_cli_accepts_basic_auth_options():
    args = build_parser().parse_args(
        [
            "run",
            "api.json",
            "--base-url",
            "https://example.test",
            "--basic-username",
            "user",
            "--basic-password",
            "pass",
        ]
    )

    assert args.basic_username == "user"
    assert args.basic_password == "pass"


def write_spec(tmp_path):
    path = tmp_path / "api.json"
    path.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "info": {
                    "title": "Basic Auth API",
                    "version": "1.0.0",
                },
                "paths": {
                    "/health": {
                        "get": {"responses": {"200": {"description": "Healthy"}}}
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def install_mock(monkeypatch, received):
    original_init = HTTPTestExecutor.__init__

    def mocked_init(self, base_url, **kwargs):
        def handler(request):
            received.append(request.headers.get("Authorization"))
            return httpx.Response(200)

        return original_init(
            self,
            base_url,
            transport=httpx.MockTransport(handler),
            **kwargs,
        )

    monkeypatch.setattr(HTTPTestExecutor, "__init__", mocked_init)


def run_cli(tmp_path, spec, extra_args):
    return main(
        [
            "run",
            str(spec),
            "--base-url",
            "https://example.test",
            "--allow-network",
            "--output",
            str(tmp_path / "report.json"),
            *extra_args,
        ]
    )


def test_cli_uses_environment_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TESTFORGE_BASIC_USERNAME", "user")
    monkeypatch.setenv("TESTFORGE_BASIC_PASSWORD", "env-secret")
    monkeypatch.delenv("TESTFORGE_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("TESTFORGE_API_KEY", raising=False)

    received = []
    install_mock(monkeypatch, received)

    exit_code = run_cli(tmp_path, write_spec(tmp_path), [])

    assert exit_code == 0
    assert received == [encode_basic_auth("user", "env-secret")]

    report = (tmp_path / "report.json").read_text(encoding="utf-8")
    output = capsys.readouterr()

    assert "env-secret" not in report
    assert "env-secret" not in output.out
    assert "env-secret" not in output.err


def test_cli_explicit_credentials_override_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("TESTFORGE_BASIC_USERNAME", "env-user")
    monkeypatch.setenv("TESTFORGE_BASIC_PASSWORD", "env-pass")
    monkeypatch.delenv("TESTFORGE_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("TESTFORGE_API_KEY", raising=False)

    received = []
    install_mock(monkeypatch, received)

    exit_code = run_cli(
        tmp_path,
        write_spec(tmp_path),
        [
            "--basic-username",
            "cli-user",
            "--basic-password",
            "cli-pass",
        ],
    )

    assert exit_code == 0
    assert received == [encode_basic_auth("cli-user", "cli-pass")]


def test_cli_rejects_incomplete_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("TESTFORGE_BASIC_USERNAME", raising=False)
    monkeypatch.delenv("TESTFORGE_BASIC_PASSWORD", raising=False)
    monkeypatch.delenv("TESTFORGE_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("TESTFORGE_API_KEY", raising=False)

    exit_code = run_cli(
        tmp_path,
        write_spec(tmp_path),
        ["--basic-username", "user"],
    )

    assert exit_code == 2
    assert "both username and password" in capsys.readouterr().err
    assert not (tmp_path / "report.json").exists()


def test_cli_rejects_basic_bearer_conflict(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("TESTFORGE_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("TESTFORGE_API_KEY", raising=False)

    exit_code = run_cli(
        tmp_path,
        write_spec(tmp_path),
        [
            "--basic-username",
            "user",
            "--basic-password",
            "pass",
            "--bearer-token",
            "token",
        ],
    )

    assert exit_code == 2
    assert "Basic and Bearer" in capsys.readouterr().err
    assert not (tmp_path / "report.json").exists()
