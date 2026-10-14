import json

import httpx
import pytest

from testforge.cli import build_parser, main
from testforge.execution_models import ExecutionStatus
from testforge.executor import HTTPTestExecutor, validate_bearer_token
from testforge.models import GeneratedTestCase, TestCategory


def make_case(headers=None):
    return GeneratedTestCase(
        test_id="AUTH-001",
        name="Authenticated request",
        category=TestCategory.POSITIVE,
        method="GET",
        path="/health",
        expected_status_codes=[200],
        headers=headers or {},
    )


def test_bearer_token_is_sent():
    received = []

    def handler(request):
        received.append(request.headers.get("Authorization"))
        return httpx.Response(200)

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        bearer_token="secret-token",
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.PASSED
    assert received == ["Bearer secret-token"]


def test_bearer_token_overrides_generated_authorization():
    received = []

    def handler(request):
        received.append(request.headers.get("Authorization"))
        return httpx.Response(200)

    case = make_case(headers={"authorization": "Bearer wrong-token"})

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        bearer_token="correct-token",
    ) as executor:
        result = executor.execute(case)

    assert result.status == ExecutionStatus.PASSED
    assert received == ["Bearer correct-token"]
    assert case.headers["authorization"] == "Bearer wrong-token"


def test_no_bearer_token_preserves_existing_headers():
    def handler(request):
        assert request.headers["Authorization"] == "Custom value"
        return httpx.Response(200)

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
    ) as executor:
        result = executor.execute(make_case(headers={"Authorization": "Custom value"}))

    assert result.status == ExecutionStatus.PASSED


@pytest.mark.parametrize(
    "token",
    ["", "hello world", "line\nbreak", "line\rbreak", "café", "token\tvalue"],
)
def test_invalid_tokens_are_rejected(token):
    with pytest.raises(ValueError, match="Bearer token"):
        validate_bearer_token(token)


def test_executor_rejects_invalid_token():
    with pytest.raises(ValueError, match="Bearer token"):
        HTTPTestExecutor(
            "https://example.test",
            transport=httpx.MockTransport(lambda request: httpx.Response(200)),
            bearer_token="invalid token",
        )


def test_token_is_redacted_from_transport_error():
    secret = "super-secret-token"

    def handler(request):
        raise httpx.ConnectError(
            f"Connection failed: {secret}",
            request=request,
        )

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        bearer_token=secret,
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.ERROR
    assert secret not in result.error_message
    assert "[REDACTED]" in result.error_message


def test_cli_accepts_bearer_token():
    args = build_parser().parse_args(
        [
            "run",
            "api.json",
            "--base-url",
            "https://example.test",
            "--bearer-token",
            "example-token",
        ]
    )

    assert args.bearer_token == "example-token"


def test_cli_bearer_token_defaults_to_none():
    args = build_parser().parse_args(
        ["run", "api.json", "--base-url", "https://example.test"]
    )

    assert args.bearer_token is None


def write_spec(tmp_path):
    path = tmp_path / "api.json"
    path.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "info": {"title": "Auth API", "version": "1.0.0"},
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


def test_cli_uses_environment_token(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TESTFORGE_BEARER_TOKEN", "env-secret")
    received = []
    install_mock(monkeypatch, received)

    exit_code = run_cli(tmp_path, write_spec(tmp_path), [])

    assert exit_code == 0
    assert received == ["Bearer env-secret"]

    report_text = (tmp_path / "report.json").read_text(encoding="utf-8")
    captured = capsys.readouterr()
    assert "env-secret" not in report_text
    assert "env-secret" not in captured.out
    assert "env-secret" not in captured.err


def test_cli_explicit_token_overrides_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("TESTFORGE_BEARER_TOKEN", "env-token")
    received = []
    install_mock(monkeypatch, received)

    exit_code = run_cli(
        tmp_path,
        write_spec(tmp_path),
        ["--bearer-token", "cli-token"],
    )

    assert exit_code == 0
    assert received == ["Bearer cli-token"]


def test_cli_rejects_invalid_environment_token_before_http(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("TESTFORGE_BEARER_TOKEN", "invalid token")

    def unexpected_execution(self, test_case):
        pytest.fail("Invalid authentication must prevent HTTP execution")

    monkeypatch.setattr(HTTPTestExecutor, "execute", unexpected_execution)

    exit_code = run_cli(tmp_path, write_spec(tmp_path), [])

    assert exit_code == 2
    assert "Bearer token" in capsys.readouterr().err
    assert not (tmp_path / "report.json").exists()
