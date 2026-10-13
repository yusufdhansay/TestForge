import httpx
import pytest

from testforge.execution_models import ExecutionStatus
from testforge.executor import HTTPTestExecutor
from testforge.models import GeneratedTestCase, TestCategory


def make_case(
    *,
    method="GET",
    path="/accounts",
    expected=None,
    path_parameters=None,
    query_parameters=None,
    headers=None,
    request_body=None,
):
    return GeneratedTestCase(
        test_id="TC-0001",
        name="Test request",
        category=TestCategory.POSITIVE,
        method=method,
        path=path,
        expected_status_codes=expected if expected is not None else [200],
        path_parameters=path_parameters or {},
        query_parameters=query_parameters or {},
        headers=headers or {},
        request_body=request_body,
    )


def test_successful_execution():
    transport = httpx.MockTransport(lambda request: httpx.Response(200))

    with HTTPTestExecutor(
        "https://example.test",
        transport=transport,
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.PASSED
    assert result.actual_status_code == 200
    assert result.response_time_ms is not None


def test_failed_status_assertion():
    transport = httpx.MockTransport(lambda request: httpx.Response(500))

    with HTTPTestExecutor(
        "https://example.test",
        transport=transport,
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.FAILED
    assert result.actual_status_code == 500


def test_unasserted_negative_case():
    transport = httpx.MockTransport(lambda request: httpx.Response(422))

    case = make_case(expected=[])
    case.category = TestCategory.NEGATIVE

    with HTTPTestExecutor(
        "https://example.test",
        transport=transport,
    ) as executor:
        result = executor.execute(case)

    assert result.status == ExecutionStatus.UNASSERTED
    assert result.actual_status_code == 422


def test_path_parameter_substitution():
    def handler(request):
        assert request.url.path == "/accounts/42"
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)

    case = make_case(
        path="/accounts/{id}",
        path_parameters={"id": 42},
    )

    with HTTPTestExecutor(
        "https://example.test",
        transport=transport,
    ) as executor:
        result = executor.execute(case)

    assert result.status == ExecutionStatus.PASSED


def test_query_parameters():
    def handler(request):
        assert request.url.params["limit"] == "10"
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)

    case = make_case(query_parameters={"limit": 10})

    with HTTPTestExecutor(
        "https://example.test",
        transport=transport,
    ) as executor:
        result = executor.execute(case)

    assert result.status == ExecutionStatus.PASSED


def test_json_request_body():
    def handler(request):
        assert request.method == "POST"
        assert request.headers["content-type"] == "application/json"
        assert request.content == b'{"name":"Alice"}'
        return httpx.Response(201)

    transport = httpx.MockTransport(handler)

    case = make_case(
        method="POST",
        expected=[201],
        request_body={"name": "Alice"},
    )

    with HTTPTestExecutor(
        "https://example.test",
        transport=transport,
        allow_state_changes=True,
    ) as executor:
        result = executor.execute(case)

    assert result.status == ExecutionStatus.PASSED


def test_unresolved_path_parameter():
    transport = httpx.MockTransport(lambda request: httpx.Response(200))

    case = make_case(path="/accounts/{id}")

    with HTTPTestExecutor(
        "https://example.test",
        transport=transport,
    ) as executor:
        result = executor.execute(case)

    assert result.status == ExecutionStatus.ERROR
    assert "Unresolved path parameters" in result.error_message


def test_network_disabled_by_default():
    import pytest

    with pytest.raises(ValueError, match="Network access is disabled"):
        HTTPTestExecutor("https://example.test")


def test_state_changes_blocked_by_default():
    transport = httpx.MockTransport(lambda request: httpx.Response(201))

    case = make_case(method="POST", expected=[201])

    with HTTPTestExecutor(
        "https://example.test",
        transport=transport,
    ) as executor:
        result = executor.execute(case)

    assert result.status == ExecutionStatus.ERROR
    assert "explicit approval" in result.error_message


def test_unapproved_real_network_target_rejected():
    import pytest

    with pytest.raises(ValueError, match="not approved"):
        HTTPTestExecutor(
            "https://example.test",
            allow_network=True,
            approved_origins={"https://approved.test"},
        )


def test_approved_origin_configuration():
    with HTTPTestExecutor(
        "https://example.test",
        allow_network=True,
        approved_origins={"https://example.test"},
    ) as executor:
        assert executor.base_url == "https://example.test"


def test_invalid_base_url_rejected():
    import pytest

    with pytest.raises(ValueError, match="Invalid base URL"):
        HTTPTestExecutor(
            "not-a-valid-url",
            transport=httpx.MockTransport(lambda request: httpx.Response(200)),
        )


def test_request_timeout():
    def handler(request):
        raise httpx.ReadTimeout(
            "Request timed out",
            request=request,
        )

    transport = httpx.MockTransport(handler)

    with HTTPTestExecutor(
        "https://example.test",
        transport=transport,
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.ERROR
    assert result.actual_status_code is None
    assert "Request timed out" in result.error_message


def test_connection_failure():
    def handler(request):
        raise httpx.ConnectError(
            "Connection refused",
            request=request,
        )

    transport = httpx.MockTransport(handler)

    with HTTPTestExecutor(
        "https://example.test",
        transport=transport,
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.ERROR
    assert result.actual_status_code is None
    assert "Connection refused" in result.error_message


def test_invalid_timeout_configuration():
    import pytest

    with pytest.raises(ValueError, match="Timeout must be positive"):
        HTTPTestExecutor(
            "https://example.test",
            transport=httpx.MockTransport(lambda request: httpx.Response(200)),
            timeout=0,
        )


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "https://other.example/data",
        "http://other.example/data",
        "//other.example/data",
        "/data?redirect=https://other.example",
        "/data#fragment",
        "/data\\other",
        "relative/path",
    ],
)
def test_executor_rejects_unsafe_paths(unsafe_path):
    requests_sent = []

    def mock_handler(request):
        requests_sent.append(request)
        return httpx.Response(200)

    transport = httpx.MockTransport(mock_handler)

    with HTTPTestExecutor(
        base_url="https://approved.example",
        transport=transport,
    ) as executor:
        test_case = GeneratedTestCase(
            test_id="unsafe-path-test",
            name="Reject unsafe API path",
            category="positive",
            method="GET",
            path=unsafe_path,
            expected_status_codes=[200],
        )

        result = executor.execute(test_case)

    assert result.status == ExecutionStatus.ERROR
    assert requests_sent == []
    assert "Unsafe API path" in result.error_message
