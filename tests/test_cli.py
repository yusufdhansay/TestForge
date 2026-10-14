import json

import httpx
import pytest

from testforge.cli import build_parser, get_version, main
from testforge.executor import HTTPTestExecutor


def test_cli_version():

    assert get_version() == "0.1.0"


def test_cli_help(capsys):

    parser = build_parser()

    with pytest.raises(SystemExit) as error:
        parser.parse_args(["--help"])

    assert error.value.code == 0

    output = capsys.readouterr().out

    assert "Automated API contract testing" in output

    assert "--version" in output


def test_cli_main_prints_help(capsys):

    exit_code = main([])

    output = capsys.readouterr().out

    assert exit_code == 0

    assert "usage: testforge" in output


def test_run_command_parses_required_arguments():

    parser = build_parser()

    args = parser.parse_args(
        [
            "run",
            "examples/banking_api.json",
            "--base-url",
            "https://banking.test",
        ]
    )

    assert args.command == "run"

    assert args.spec == "examples/banking_api.json"

    assert args.base_url == "https://banking.test"

    assert args.report == "json"

    assert args.output is None

    assert args.allow_network is False

    assert args.allow_state_changes is False


def test_run_command_parses_optional_arguments():

    parser = build_parser()

    args = parser.parse_args(
        [
            "run",
            "examples/banking_api.json",
            "--base-url",
            "https://banking.test",
            "--report",
            "html",
            "--output",
            "reports/result.html",
            "--allow-network",
            "--allow-state-changes",
        ]
    )

    assert args.report == "html"

    assert args.output == "reports/result.html"

    assert args.allow_network is True

    assert args.allow_state_changes is True


def test_run_requires_base_url():

    parser = build_parser()

    with pytest.raises(SystemExit) as error:
        parser.parse_args(["run", "examples/banking_api.json"])

    assert error.value.code == 2


def test_run_rejects_unsupported_report_format():

    parser = build_parser()

    with pytest.raises(SystemExit) as error:
        parser.parse_args(
            [
                "run",
                "examples/banking_api.json",
                "--base-url",
                "https://banking.test",
                "--report",
                "xml",
            ]
        )

    assert error.value.code == 2


def test_run_refuses_network_without_explicit_approval(capsys):

    exit_code = main(
        [
            "run",
            "examples/banking_api.json",
            "--base-url",
            "https://banking.test",
        ]
    )

    assert exit_code == 2

    assert "Network access is disabled" in capsys.readouterr().err


def test_run_rejects_invalid_base_url(capsys):

    exit_code = main(
        [
            "run",
            "examples/banking_api.json",
            "--base-url",
            "not-a-url",
            "--allow-network",
        ]
    )

    assert exit_code == 2

    assert "Invalid base URL" in capsys.readouterr().err


def test_run_rejects_url_with_credentials(capsys):

    exit_code = main(
        [
            "run",
            "examples/banking_api.json",
            "--base-url",
            "https://user:password@banking.test",
            "--allow-network",
        ]
    )

    assert exit_code == 2

    assert "Invalid base URL" in capsys.readouterr().err


def test_run_generates_json_report_with_mock_http(tmp_path, monkeypatch, capsys):

    spec_path = tmp_path / "api.json"

    report_path = tmp_path / "report.json"

    spec_path.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "info": {
                    "title": "Mock API",
                    "version": "1.0.0",
                },
                "paths": {
                    "/health": {
                        "get": {
                            "responses": {
                                "200": {
                                    "description": "Healthy",
                                }
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    original_init = HTTPTestExecutor.__init__

    def mocked_init(self, base_url, **kwargs):

        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"status": "ok"},
            )
        )

        return original_init(
            self,
            base_url,
            transport=transport,
            **kwargs,
        )

    monkeypatch.setattr(HTTPTestExecutor, "__init__", mocked_init)

    exit_code = main(
        [
            "run",
            str(spec_path),
            "--base-url",
            "https://mock.test",
            "--allow-network",
            "--output",
            str(report_path),
        ]
    )

    assert exit_code == 0

    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["summary"]["total"] >= 1

    assert report["summary"]["failed"] == 0

    assert report["summary"]["errors"] == 0

    output = capsys.readouterr().out

    assert "Report:" in output


def test_run_returns_exit_code_one_for_failed_contract(tmp_path, monkeypatch, capsys):

    spec_path = tmp_path / "api.json"

    report_path = tmp_path / "failed-report.json"

    spec_path.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "info": {
                    "title": "Failure Test API",
                    "version": "1.0.0",
                },
                "paths": {
                    "/health": {
                        "get": {
                            "responses": {
                                "200": {
                                    "description": "Healthy",
                                }
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    original_init = HTTPTestExecutor.__init__

    def mocked_init(self, base_url, **kwargs):

        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                500,
                json={"error": "Internal server error"},
            )
        )

        return original_init(
            self,
            base_url,
            transport=transport,
            **kwargs,
        )

    monkeypatch.setattr(HTTPTestExecutor, "__init__", mocked_init)

    exit_code = main(
        [
            "run",
            str(spec_path),
            "--base-url",
            "https://mock.test",
            "--allow-network",
            "--output",
            str(report_path),
        ]
    )

    assert exit_code == 1

    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["summary"]["failed"] >= 1

    assert report["summary"]["passed"] == 0

    output = capsys.readouterr().out

    assert "Failed:" in output


def test_run_generates_html_report_with_mock_http(tmp_path, monkeypatch, capsys):

    spec_path = tmp_path / "api.json"

    report_path = tmp_path / "report.html"

    spec_path.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "info": {
                    "title": "Mock API",
                    "version": "1.0.0",
                },
                "paths": {
                    "/health": {
                        "get": {
                            "responses": {
                                "200": {
                                    "description": "Healthy",
                                }
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    original_init = HTTPTestExecutor.__init__

    def mocked_init(self, base_url, **kwargs):

        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"status": "ok"},
            )
        )

        return original_init(
            self,
            base_url,
            transport=transport,
            **kwargs,
        )

    monkeypatch.setattr(HTTPTestExecutor, "__init__", mocked_init)

    exit_code = main(
        [
            "run",
            str(spec_path),
            "--base-url",
            "https://mock.test",
            "--allow-network",
            "--report",
            "html",
            "--output",
            str(report_path),
        ]
    )

    assert exit_code == 0

    assert report_path.exists()

    html = report_path.read_text(encoding="utf-8")

    assert "<!DOCTYPE html>" in html

    assert "TestForge Execution Report" in html

    assert "Individual Test Results" in html

    assert "PASSED" in html

    output = capsys.readouterr().out

    assert "Report:" in output


@pytest.mark.parametrize(
    ("report_format", "extension"),
    [
        ("json", "json"),
        ("html", "html"),
    ],
)
def test_run_refuses_to_overwrite_existing_report(
    tmp_path, monkeypatch, capsys, report_format, extension
):

    spec_path = tmp_path / "api.json"

    report_path = tmp_path / f"existing-report.{extension}"

    spec_path.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "info": {
                    "title": "Overwrite Protection API",
                    "version": "1.0.0",
                },
                "paths": {
                    "/health": {
                        "get": {
                            "responses": {
                                "200": {
                                    "description": "Healthy",
                                }
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    original_content = "DO NOT OVERWRITE"

    report_path.write_text(original_content, encoding="utf-8")

    original_init = HTTPTestExecutor.__init__

    def mocked_init(self, base_url, **kwargs):

        transport = httpx.MockTransport(lambda request: httpx.Response(200))

        return original_init(
            self,
            base_url,
            transport=transport,
            **kwargs,
        )

    monkeypatch.setattr(HTTPTestExecutor, "__init__", mocked_init)

    exit_code = main(
        [
            "run",
            str(spec_path),
            "--base-url",
            "https://mock.test",
            "--allow-network",
            "--report",
            report_format,
            "--output",
            str(report_path),
        ]
    )

    assert exit_code == 2

    assert report_path.read_text(encoding="utf-8") == original_content

    assert "Error:" in capsys.readouterr().err


def test_existing_report_prevents_http_execution(tmp_path, monkeypatch):

    spec_path = tmp_path / "api.json"

    report_path = tmp_path / "report.json"

    spec_path.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "info": {
                    "title": "Safety Test API",
                    "version": "1.0.0",
                },
                "paths": {
                    "/health": {
                        "get": {
                            "responses": {
                                "200": {
                                    "description": "Healthy",
                                }
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    report_path.write_text("EXISTING REPORT", encoding="utf-8")

    def unexpected_execution(self, test_case):

        pytest.fail("HTTP execution must not occur when report already exists")

    monkeypatch.setattr(
        HTTPTestExecutor,
        "execute",
        unexpected_execution,
    )

    exit_code = main(
        [
            "run",
            str(spec_path),
            "--base-url",
            "https://mock.test",
            "--allow-network",
            "--output",
            str(report_path),
        ]
    )

    assert exit_code == 2

    assert report_path.read_text(encoding="utf-8") == "EXISTING REPORT"


@pytest.mark.parametrize(
    ("report_format", "output_name", "expected_error"),
    [
        ("json", "report.html", "JSON file"),
        ("html", "report.json", "HTML file"),
        ("json", "missing/report.json", "Output directory does not exist"),
        ("html", "missing/report.html", "Output directory does not exist"),
    ],
)
def test_invalid_report_destination_prevents_execution(
    tmp_path,
    monkeypatch,
    capsys,
    report_format,
    output_name,
    expected_error,
):

    spec_path = tmp_path / "api.json"

    output_path = tmp_path / output_name

    spec_path.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "info": {
                    "title": "Output Validation API",
                    "version": "1.0.0",
                },
                "paths": {
                    "/health": {
                        "get": {
                            "responses": {
                                "200": {
                                    "description": "Healthy",
                                }
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    def unexpected_execution(self, test_case):

        pytest.fail("HTTP execution must not occur for an invalid report destination")

    monkeypatch.setattr(
        HTTPTestExecutor,
        "execute",
        unexpected_execution,
    )

    exit_code = main(
        [
            "run",
            str(spec_path),
            "--base-url",
            "https://mock.test",
            "--allow-network",
            "--report",
            report_format,
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 2

    assert expected_error in capsys.readouterr().err

    assert not output_path.exists()


def test_run_blocks_state_changing_requests_by_default(tmp_path, monkeypatch):

    spec_path = tmp_path / "api.json"

    report_path = tmp_path / "report.json"

    spec_path.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "info": {
                    "title": "State Change Safety API",
                    "version": "1.0.0",
                },
                "paths": {
                    "/transactions": {
                        "post": {
                            "responses": {
                                "201": {
                                    "description": "Created",
                                }
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    requests_sent = []

    def mock_handler(request):

        requests_sent.append(request)

        return httpx.Response(201)

    original_init = HTTPTestExecutor.__init__

    def mocked_init(self, base_url, **kwargs):

        return original_init(
            self,
            base_url,
            transport=httpx.MockTransport(mock_handler),
            **kwargs,
        )

    monkeypatch.setattr(HTTPTestExecutor, "__init__", mocked_init)

    exit_code = main(
        [
            "run",
            str(spec_path),
            "--base-url",
            "https://mock.test",
            "--allow-network",
            "--output",
            str(report_path),
        ]
    )

    assert exit_code == 1

    assert requests_sent == []

    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["summary"]["errors"] >= 1


def test_run_allows_state_changes_with_explicit_approval(tmp_path, monkeypatch):

    spec_path = tmp_path / "api.json"

    report_path = tmp_path / "report.json"

    spec_path.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "info": {
                    "title": "State Change Approval API",
                    "version": "1.0.0",
                },
                "paths": {
                    "/transactions": {
                        "post": {
                            "responses": {
                                "201": {
                                    "description": "Created",
                                }
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    requests_sent = []

    def mock_handler(request):

        requests_sent.append(request)

        return httpx.Response(201)

    original_init = HTTPTestExecutor.__init__

    def mocked_init(self, base_url, **kwargs):

        return original_init(
            self,
            base_url,
            transport=httpx.MockTransport(mock_handler),
            **kwargs,
        )

    monkeypatch.setattr(HTTPTestExecutor, "__init__", mocked_init)

    exit_code = main(
        [
            "run",
            str(spec_path),
            "--base-url",
            "https://mock.test",
            "--allow-network",
            "--allow-state-changes",
            "--output",
            str(report_path),
        ]
    )

    assert exit_code == 0

    assert len(requests_sent) >= 1

    assert all(request.method == "POST" for request in requests_sent)

    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["summary"]["errors"] == 0

    assert report["summary"]["failed"] == 0


def test_run_max_response_time_defaults_to_none():
    args = build_parser().parse_args(
        ["run", "examples/banking_api.json", "--base-url", "https://banking.test"]
    )
    assert args.max_response_time is None


def test_run_accepts_max_response_time():
    args = build_parser().parse_args(
        [
            "run",
            "examples/banking_api.json",
            "--base-url",
            "https://banking.test",
            "--max-response-time",
            "500.5",
        ]
    )
    assert args.max_response_time == 500.5


@pytest.mark.parametrize("invalid", ["0", "-1", "abc", "nan", "inf", "-inf"])
def test_run_rejects_invalid_max_response_time(invalid):
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(
            [
                "run",
                "examples/banking_api.json",
                "--base-url",
                "https://banking.test",
                "--max-response-time",
                invalid,
            ]
        )
    assert error.value.code == 2


def test_run_applies_max_response_time_to_generated_cases(tmp_path, monkeypatch):
    from unittest.mock import patch

    spec_path = tmp_path / "api.json"
    report_path = tmp_path / "report.json"
    spec_path.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "info": {"title": "Timing API", "version": "1.0.0"},
                "paths": {
                    "/health": {
                        "get": {"responses": {"200": {"description": "Healthy"}}}
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    original_init = HTTPTestExecutor.__init__

    def mocked_init(self, base_url, **kwargs):
        return original_init(
            self,
            base_url,
            transport=httpx.MockTransport(lambda request: httpx.Response(200)),
            **kwargs,
        )

    monkeypatch.setattr(HTTPTestExecutor, "__init__", mocked_init)

    with patch("testforge.executor.perf_counter", side_effect=lambda: 10.0):
        exit_code = main(
            [
                "run",
                str(spec_path),
                "--base-url",
                "https://mock.test",
                "--allow-network",
                "--max-response-time",
                "500",
                "--output",
                str(report_path),
            ]
        )

    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["summary"]["failed"] == 0


def test_run_reports_latency_failure(tmp_path, monkeypatch):
    from unittest.mock import patch

    spec_path = tmp_path / "api.json"
    report_path = tmp_path / "report.json"
    spec_path.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "info": {"title": "Timing API", "version": "1.0.0"},
                "paths": {
                    "/health": {
                        "get": {"responses": {"200": {"description": "Healthy"}}}
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    original_init = HTTPTestExecutor.__init__

    def mocked_init(self, base_url, **kwargs):
        return original_init(
            self,
            base_url,
            transport=httpx.MockTransport(lambda request: httpx.Response(200)),
            **kwargs,
        )

    monkeypatch.setattr(HTTPTestExecutor, "__init__", mocked_init)

    # Each generated test receives a deterministic 750 ms response time.
    clock = iter([10.0, 10.75] * 100)
    with patch("testforge.executor.perf_counter", side_effect=lambda: next(clock)):
        exit_code = main(
            [
                "run",
                str(spec_path),
                "--base-url",
                "https://mock.test",
                "--allow-network",
                "--max-response-time",
                "500",
                "--output",
                str(report_path),
            ]
        )

    assert exit_code == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["summary"]["failed"] >= 1
