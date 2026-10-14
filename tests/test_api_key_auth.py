import json

import httpx
import pytest

from testforge.cli import build_parser, main
from testforge.execution_models import ExecutionStatus
from testforge.executor import (
    HTTPTestExecutor,
    validate_api_key,
    validate_api_key_configuration,
)
from testforge.models import GeneratedTestCase, TestCategory


def make_case(*, headers=None, query_parameters=None):
    return GeneratedTestCase(
        test_id="APIKEY-001",
        name="API key authentication",
        category=TestCategory.POSITIVE,
        method="GET",
        path="/health",
        expected_status_codes=[200],
        headers=headers or {},
        query_parameters=query_parameters or {},
    )


def test_api_key_header_is_sent():
    def handler(request):
        assert request.headers["X-API-Key"] == "secret-key"
        return httpx.Response(200)

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        api_key="secret-key",
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.PASSED


def test_custom_api_key_header():
    def handler(request):
        assert request.headers["X-Custom-Key"] == "custom-secret"
        return httpx.Response(200)

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        api_key="custom-secret",
        api_key_name="X-Custom-Key",
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.PASSED


def test_api_key_header_overrides_generated_header():
    def handler(request):
        assert request.headers["X-API-Key"] == "correct-key"
        return httpx.Response(200)

    case = make_case(headers={"x-api-key": "wrong-key"})

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        api_key="correct-key",
    ) as executor:
        result = executor.execute(case)

    assert result.status == ExecutionStatus.PASSED
    assert case.headers["x-api-key"] == "wrong-key"


def test_api_key_query_parameter_is_sent():
    def handler(request):
        assert request.url.params["api_key"] == "query-secret"
        return httpx.Response(200)

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        api_key="query-secret",
        api_key_location="query",
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.PASSED


def test_custom_query_parameter_overrides_generated_value():
    def handler(request):
        assert request.url.params["access_key"] == "correct-key"
        assert request.url.params["page"] == "2"
        return httpx.Response(200)

    case = make_case(
        query_parameters={
            "access_key": "wrong-key",
            "page": 2,
        }
    )

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        api_key="correct-key",
        api_key_name="access_key",
        api_key_location="query",
    ) as executor:
        result = executor.execute(case)

    assert result.status == ExecutionStatus.PASSED
    assert case.query_parameters["access_key"] == "wrong-key"


def test_bearer_and_api_key_can_coexist():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer bearer-secret"
        assert request.headers["X-API-Key"] == "api-secret"
        return httpx.Response(200)

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        bearer_token="bearer-secret",
        api_key="api-secret",
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.PASSED


def test_bearer_and_authorization_api_key_conflict():
    with pytest.raises(ValueError, match="conflict"):
        HTTPTestExecutor(
            "https://example.test",
            transport=httpx.MockTransport(lambda request: httpx.Response(200)),
            bearer_token="bearer-secret",
            api_key="api-secret",
            api_key_name="Authorization",
        )


@pytest.mark.parametrize(
    "key",
    ["", "with space", "line\nbreak", "line\rbreak", "café", "tab\tkey"],
)
def test_invalid_api_keys_are_rejected(key):
    with pytest.raises(ValueError, match="API key"):
        validate_api_key(key)


@pytest.mark.parametrize(
    "name",
    ["Bad Header", "Bad:Header", "Bad\nHeader", ""],
)
def test_invalid_header_names_are_rejected(name):
    with pytest.raises(ValueError, match="header name"):
        validate_api_key_configuration(
            "valid-key",
            name,
            "header",
        )


@pytest.mark.parametrize(
    "name",
    ["bad name", "bad&name", "bad?name", ""],
)
def test_invalid_query_names_are_rejected(name):
    with pytest.raises(ValueError, match="query parameter name"):
        validate_api_key_configuration(
            "valid-key",
            name,
            "query",
        )


def test_invalid_location_is_rejected():
    with pytest.raises(ValueError, match="location"):
        validate_api_key_configuration(
            "valid-key",
            "X-API-Key",
            "cookie",
        )


def test_name_without_key_is_rejected():
    with pytest.raises(ValueError, match="requires an API key"):
        validate_api_key_configuration(
            None,
            "X-API-Key",
            "header",
        )


def test_api_key_is_redacted_from_transport_errors():
    secret = "very-secret-api-key"

    def handler(request):
        raise httpx.ConnectError(
            f"Connection failed for {secret}",
            request=request,
        )

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        api_key=secret,
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.ERROR
    assert secret not in result.error_message
    assert "[REDACTED]" in result.error_message


def test_api_key_query_is_redacted_from_url_errors():
    secret = "query-secret-value"

    def handler(request):
        raise httpx.ConnectError(
            f"Request failed: {request.url}",
            request=request,
        )

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        api_key=secret,
        api_key_location="query",
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.ERROR
    assert secret not in result.error_message
    assert "[REDACTED]" in result.error_message


def test_cli_parses_api_key_options():
    args = build_parser().parse_args(
        [
            "run",
            "api.json",
            "--base-url",
            "https://example.test",
            "--api-key",
            "example-key",
            "--api-key-name",
            "X-Custom-Key",
            "--api-key-in",
            "header",
        ]
    )

    assert args.api_key == "example-key"
    assert args.api_key_name == "X-Custom-Key"
    assert args.api_key_in == "header"


def write_spec(tmp_path):
    path = tmp_path / "api.json"
    path.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "info": {
                    "title": "API Key Test",
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
            received.append(
                {
                    "headers": dict(request.headers),
                    "query": dict(request.url.params),
                }
            )
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


def test_cli_uses_environment_api_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TESTFORGE_API_KEY", "env-api-secret")
    monkeypatch.delenv("TESTFORGE_BEARER_TOKEN", raising=False)

    received = []
    install_mock(monkeypatch, received)

    exit_code = run_cli(
        tmp_path,
        write_spec(tmp_path),
        [],
    )

    assert exit_code == 0
    assert received[0]["headers"]["x-api-key"] == "env-api-secret"

    report = (tmp_path / "report.json").read_text(encoding="utf-8")
    captured = capsys.readouterr()

    assert "env-api-secret" not in report
    assert "env-api-secret" not in captured.out
    assert "env-api-secret" not in captured.err


def test_cli_explicit_key_overrides_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("TESTFORGE_API_KEY", "env-secret")
    monkeypatch.delenv("TESTFORGE_BEARER_TOKEN", raising=False)

    received = []
    install_mock(monkeypatch, received)

    exit_code = run_cli(
        tmp_path,
        write_spec(tmp_path),
        ["--api-key", "cli-secret"],
    )

    assert exit_code == 0
    assert received[0]["headers"]["x-api-key"] == "cli-secret"


def test_cli_supports_query_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("TESTFORGE_API_KEY", "query-secret")
    monkeypatch.delenv("TESTFORGE_BEARER_TOKEN", raising=False)

    received = []
    install_mock(monkeypatch, received)

    exit_code = run_cli(
        tmp_path,
        write_spec(tmp_path),
        [
            "--api-key-in",
            "query",
            "--api-key-name",
            "access_key",
        ],
    )

    assert exit_code == 0
    assert received[0]["query"]["access_key"] == "query-secret"


def test_cli_rejects_invalid_api_key_before_execution(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TESTFORGE_API_KEY", "invalid key")
    monkeypatch.delenv("TESTFORGE_BEARER_TOKEN", raising=False)

    def unexpected_execution(self, test_case):
        pytest.fail("Invalid credentials must prevent HTTP execution")

    monkeypatch.setattr(
        HTTPTestExecutor,
        "execute",
        unexpected_execution,
    )

    exit_code = run_cli(
        tmp_path,
        write_spec(tmp_path),
        [],
    )

    assert exit_code == 2
    assert "API key" in capsys.readouterr().err
    assert not (tmp_path / "report.json").exists()


def test_cli_rejects_missing_api_key_for_named_header(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("TESTFORGE_API_KEY", raising=False)
    monkeypatch.delenv("TESTFORGE_BEARER_TOKEN", raising=False)

    exit_code = run_cli(
        tmp_path,
        write_spec(tmp_path),
        ["--api-key-name", "X-Custom-Key"],
    )

    assert exit_code == 2
    assert "requires an API key" in capsys.readouterr().err
