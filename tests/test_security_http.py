import httpx

from testforge.execution_models import ExecutionStatus
from testforge.executor import HTTPTestExecutor
from testforge.models import GeneratedTestCase, TestCategory
from testforge.security_routing import OperationAuth


def make_case(path="/users"):
    return GeneratedTestCase(
        test_id="SEC-001",
        name="Authentication routing test",
        category=TestCategory.POSITIVE,
        method="GET",
        path=path,
        expected_status_codes=[200],
    )


def test_public_endpoint_does_not_receive_bearer_token():
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200)

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        bearer_token="secret-token",
        operation_auth={
            ("GET", "/health"): OperationAuth(),
        },
    ) as executor:
        result = executor.execute(make_case("/health"))

    assert result.status == ExecutionStatus.PASSED
    assert len(captured) == 1
    assert "authorization" not in captured[0].headers


def test_protected_endpoint_receives_bearer_token():
    def handler(request):
        assert request.headers["authorization"] == "Bearer secret-token"
        return httpx.Response(200)

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        bearer_token="secret-token",
        operation_auth={
            ("GET", "/users"): OperationAuth(bearer=True),
        },
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.PASSED


def test_public_endpoint_does_not_receive_basic_auth():
    def handler(request):
        assert "authorization" not in request.headers
        return httpx.Response(200)

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        basic_username="admin",
        basic_password="secret",
        operation_auth={
            ("GET", "/health"): OperationAuth(),
        },
    ) as executor:
        result = executor.execute(make_case("/health"))

    assert result.status == ExecutionStatus.PASSED


def test_protected_endpoint_receives_basic_auth():
    def handler(request):
        assert request.headers["authorization"].startswith("Basic ")
        return httpx.Response(200)

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        basic_username="admin",
        basic_password="secret",
        operation_auth={
            ("GET", "/users"): OperationAuth(basic=True),
        },
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.PASSED


def test_public_endpoint_does_not_receive_api_key():
    def handler(request):
        assert "x-api-key" not in request.headers
        return httpx.Response(200)

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        api_key="secret-key",
        api_key_name="X-API-Key",
        operation_auth={
            ("GET", "/health"): OperationAuth(),
        },
    ) as executor:
        result = executor.execute(make_case("/health"))

    assert result.status == ExecutionStatus.PASSED


def test_protected_endpoint_receives_api_key():
    def handler(request):
        assert request.headers["x-api-key"] == "secret-key"
        return httpx.Response(200)

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        api_key="secret-key",
        api_key_name="X-API-Key",
        operation_auth={
            ("GET", "/users"): OperationAuth(api_key=True),
        },
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.PASSED


def test_query_api_key_is_not_sent_to_public_endpoint():
    def handler(request):
        assert "api_key" not in request.url.params
        return httpx.Response(200)

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        api_key="secret-key",
        api_key_name="api_key",
        api_key_location="query",
        operation_auth={
            ("GET", "/health"): OperationAuth(),
        },
    ) as executor:
        result = executor.execute(make_case("/health"))

    assert result.status == ExecutionStatus.PASSED


def test_query_api_key_is_sent_to_protected_endpoint():
    def handler(request):
        assert request.url.params["api_key"] == "secret-key"
        return httpx.Response(200)

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        api_key="secret-key",
        api_key_name="api_key",
        api_key_location="query",
        operation_auth={
            ("GET", "/users"): OperationAuth(api_key=True),
        },
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.PASSED


def test_and_requirement_sends_bearer_and_api_key():
    def handler(request):
        assert request.headers["authorization"] == "Bearer token"
        assert request.headers["x-api-key"] == "key"
        return httpx.Response(200)

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        bearer_token="token",
        api_key="key",
        api_key_name="X-API-Key",
        operation_auth={
            ("GET", "/users"): OperationAuth(
                bearer=True,
                api_key=True,
            ),
        },
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.PASSED


def test_missing_operation_auth_blocks_request():
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200)

    with HTTPTestExecutor(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        bearer_token="secret-token",
        operation_auth={},
    ) as executor:
        result = executor.execute(make_case())

    assert result.status == ExecutionStatus.ERROR
    assert captured == []
    assert "No security configuration" in result.error_message
