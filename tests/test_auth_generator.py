"""Tests for opt-in negative authentication scenario generation."""

import pytest

from testforge.auth_generator import AuthMutation, generate_auth_scenarios
from testforge.security import analyze_security
from testforge.security_routing import OperationAuth


def document(security, *, operation_security=None):
    operation = {"responses": {"200": {"description": "OK"}}}
    if operation_security is not None:
        operation["security"] = operation_security
    return {
        "openapi": "3.0.3",
        "info": {"title": "Auth", "version": "1"},
        "components": {
            "securitySchemes": {
                "Bearer": {"type": "http", "scheme": "bearer"},
                "Basic": {"type": "http", "scheme": "basic"},
                "Key": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
            }
        },
        "security": security,
        "paths": {"/users": {"get": operation}},
    }


def test_bearer_generates_three_scenarios():
    analysis = analyze_security(document([{"Bearer": []}]))
    cases = generate_auth_scenarios(
        analysis, {("GET", "/users"): OperationAuth(bearer=True)}
    )
    assert [case.mutation for case in cases] == [
        AuthMutation.MISSING,
        AuthMutation.INVALID,
        AuthMutation.MALFORMED,
    ]
    assert all(case.expected_status_codes == (401,) for case in cases)
    assert all(case.auth_kind == "bearer" for case in cases)


def test_basic_generates_three_scenarios():
    analysis = analyze_security(document([{"Basic": []}]))
    cases = generate_auth_scenarios(
        analysis, {("GET", "/users"): OperationAuth(basic=True)}
    )
    assert len(cases) == 3
    assert cases[-1].mutation == AuthMutation.MALFORMED


def test_api_key_generates_two_scenarios():
    analysis = analyze_security(document([{"Key": []}]))
    cases = generate_auth_scenarios(
        analysis, {("GET", "/users"): OperationAuth(api_key=True)}
    )
    assert [case.mutation for case in cases] == [
        AuthMutation.MISSING,
        AuthMutation.INVALID,
    ]


def test_and_requirement_tests_each_credential():
    analysis = analyze_security(document([{"Bearer": [], "Key": []}]))
    cases = generate_auth_scenarios(
        analysis,
        {("GET", "/users"): OperationAuth(bearer=True, api_key=True)},
    )
    assert len(cases) == 5
    assert {case.auth_kind for case in cases} == {"bearer", "api_key"}


def test_or_requirement_tests_only_selected_alternative():
    analysis = analyze_security(document([{"Bearer": []}, {"Key": []}]))
    cases = generate_auth_scenarios(
        analysis, {("GET", "/users"): OperationAuth(api_key=True)}
    )
    assert len(cases) == 2
    assert all(case.auth_kind == "api_key" for case in cases)


def test_public_operation_generates_no_scenarios():
    analysis = analyze_security(document([{"Bearer": []}], operation_security=[]))
    assert generate_auth_scenarios(analysis, {("GET", "/users"): OperationAuth()}) == []


def test_missing_route_fails_closed():
    analysis = analyze_security(document([{"Bearer": []}]))
    with pytest.raises(ValueError, match="Missing authentication routing"):
        generate_auth_scenarios(analysis, {})


def test_empty_protected_route_fails_closed():
    analysis = analyze_security(document([{"Bearer": []}]))
    with pytest.raises(ValueError, match="No authentication method selected"):
        generate_auth_scenarios(analysis, {("GET", "/users"): OperationAuth()})


def test_no_real_credentials_are_stored():
    analysis = analyze_security(document([{"Bearer": []}]))
    cases = generate_auth_scenarios(
        analysis, {("GET", "/users"): OperationAuth(bearer=True)}
    )
    assert all("token" not in vars(case) for case in cases)
