import pytest

from testforge.security import analyze_security
from testforge.security_routing import OperationAuth, build_operation_auth


def make_analysis(global_security, paths, schemes=None):
    return analyze_security(
        {
            "openapi": "3.0.3",
            "info": {"title": "Test", "version": "1"},
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
            "security": global_security,
            "paths": paths,
        }
    )


def operation(responses=None, security=None):
    result = {"responses": responses or {"200": {"description": "OK"}}}
    if security is not None:
        result["security"] = security
    return result


def test_public_override_receives_no_credentials():
    analysis = make_analysis(
        [{"BearerAuth": []}],
        {
            "/health": {
                "get": operation(security=[]),
            },
            "/users": {
                "get": operation(),
            },
        },
    )

    routing = build_operation_auth(
        analysis,
        bearer_token="secret",
    )

    assert routing[("GET", "/health")] == OperationAuth()
    assert routing[("GET", "/users")].bearer is True


def test_or_alternative_selects_available_api_key():
    analysis = make_analysis(
        [
            {"BearerAuth": []},
            {"ApiKey": []},
        ],
        {"/users": {"get": operation()}},
    )

    routing = build_operation_auth(
        analysis,
        api_key="secret",
        api_key_name="X-API-Key",
    )

    assert routing[("GET", "/users")] == OperationAuth(api_key=True)


def test_and_requirement_selects_both_credentials():
    analysis = make_analysis(
        [{"BearerAuth": [], "ApiKey": []}],
        {"/users": {"get": operation()}},
    )

    routing = build_operation_auth(
        analysis,
        bearer_token="token",
        api_key="key",
        api_key_name="X-API-Key",
    )

    assert routing[("GET", "/users")] == OperationAuth(
        bearer=True,
        api_key=True,
    )


def test_missing_credentials_are_rejected():
    analysis = make_analysis(
        [{"BearerAuth": []}],
        {"/users": {"get": operation()}},
    )

    with pytest.raises(ValueError, match="GET /users"):
        build_operation_auth(analysis)


def test_mismatched_api_key_name_is_rejected():
    analysis = make_analysis(
        [{"ApiKey": []}],
        {"/users": {"get": operation()}},
    )

    with pytest.raises(ValueError, match="GET /users"):
        build_operation_auth(
            analysis,
            api_key="secret",
            api_key_name="Wrong-Header",
        )


def test_unsupported_authentication_is_rejected():
    analysis = make_analysis(
        [{"OAuth": []}],
        {"/users": {"get": operation()}},
        schemes={
            "OAuth": {
                "type": "oauth2",
                "flows": {},
            }
        },
    )

    with pytest.raises(ValueError, match="GET /users"):
        build_operation_auth(analysis, bearer_token="token")


def test_anonymous_alternative_receives_no_credentials():
    analysis = make_analysis(
        [{}, {"BearerAuth": []}],
        {"/health": {"get": operation()}},
    )

    routing = build_operation_auth(
        analysis,
        bearer_token="secret",
    )

    assert routing[("GET", "/health")] == OperationAuth()
