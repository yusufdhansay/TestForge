import pytest

from testforge.security import (
    analyze_security,
    credentials_satisfy,
    detect_security_scheme,
    parse_requirements,
)


def make_document(
    *,
    schemes=None,
    global_security=None,
    paths=None,
):
    document = {
        "openapi": "3.1.0",
        "info": {
            "title": "Security Test API",
            "version": "1.0.0",
        },
        "components": {
            "securitySchemes": schemes or {},
        },
        "paths": paths
        if paths is not None
        else {
            "/health": {
                "get": {
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    if global_security is not None:
        document["security"] = global_security

    return document


def test_detect_bearer_authentication():
    scheme = detect_security_scheme(
        "BearerAuth",
        {"type": "http", "scheme": "bearer"},
    )

    assert scheme.name == "BearerAuth"
    assert scheme.kind == "bearer"


def test_detect_basic_authentication():
    scheme = detect_security_scheme(
        "BasicAuth",
        {"type": "http", "scheme": "basic"},
    )

    assert scheme.kind == "basic"


def test_http_scheme_is_case_insensitive():
    scheme = detect_security_scheme(
        "BearerAuth",
        {"type": "http", "scheme": "Bearer"},
    )

    assert scheme.kind == "bearer"


@pytest.mark.parametrize("location", ["header", "query"])
def test_detect_api_key(location):
    scheme = detect_security_scheme(
        "ApiKey",
        {
            "type": "apiKey",
            "in": location,
            "name": "X-API-Key",
        },
    )

    assert scheme.kind == "apiKey"
    assert scheme.location == location
    assert scheme.parameter_name == "X-API-Key"


@pytest.mark.parametrize(
    "definition",
    [
        {"type": "oauth2", "flows": {}},
        {"type": "openIdConnect", "openIdConnectUrl": "https://example.test"},
        {"type": "http", "scheme": "digest"},
        {"type": "mutualTLS"},
        {"type": "apiKey", "in": "cookie", "name": "session"},
        {"type": "apiKey", "in": "header"},
    ],
)
def test_unsupported_security_schemes(definition):
    scheme = detect_security_scheme("Unsupported", definition)

    assert scheme.kind == "unsupported"


def test_global_security_is_inherited():
    document = make_document(
        schemes={
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
            }
        },
        global_security=[{"BearerAuth": []}],
    )

    analysis = analyze_security(document)
    operation = analysis.operations[0]

    assert operation.public is False
    assert operation.requirements[0].schemes == ("BearerAuth",)


def test_operation_security_overrides_global_security():
    document = make_document(
        global_security=[{"BearerAuth": []}],
        paths={
            "/items": {
                "get": {
                    "security": [{"ApiKey": []}],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    )

    operation = analyze_security(document).operations[0]

    assert operation.requirements[0].schemes == ("ApiKey",)


def test_empty_operation_security_disables_global_security():
    document = make_document(
        global_security=[{"BearerAuth": []}],
        paths={
            "/health": {
                "get": {
                    "security": [],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    )

    operation = analyze_security(document).operations[0]

    assert operation.public is True
    assert operation.requirements == ()


def test_empty_requirement_object_allows_anonymous_access():
    document = make_document(
        global_security=[
            {},
            {"BearerAuth": []},
        ],
    )

    operation = analyze_security(document).operations[0]

    assert operation.public is True


def test_no_security_declaration_means_public():
    operation = analyze_security(make_document()).operations[0]

    assert operation.public is True


def test_security_requirements_preserve_or_alternatives():
    requirements = parse_requirements(
        [
            {"BearerAuth": []},
            {"ApiKey": []},
        ]
    )

    assert len(requirements) == 2
    assert requirements[0].schemes == ("BearerAuth",)
    assert requirements[1].schemes == ("ApiKey",)


def test_security_requirements_preserve_and_groups():
    requirements = parse_requirements(
        [
            {
                "BearerAuth": [],
                "ApiKey": [],
            }
        ]
    )

    assert len(requirements) == 1
    assert requirements[0].schemes == ("BearerAuth", "ApiKey")


def test_or_requirement_accepts_either_scheme():
    requirements = parse_requirements(
        [
            {"BearerAuth": []},
            {"ApiKey": []},
        ]
    )

    assert credentials_satisfy(requirements, {"BearerAuth"})
    assert credentials_satisfy(requirements, {"ApiKey"})
    assert not credentials_satisfy(requirements, set())


def test_and_requirement_requires_both_schemes():
    requirements = parse_requirements(
        [
            {
                "BearerAuth": [],
                "ApiKey": [],
            }
        ]
    )

    assert credentials_satisfy(
        requirements,
        {"BearerAuth", "ApiKey"},
    )
    assert not credentials_satisfy(
        requirements,
        {"BearerAuth"},
    )


def test_empty_requirements_allow_anonymous_access():
    assert credentials_satisfy((), set())


def test_empty_requirement_object_matches_without_credentials():
    requirements = parse_requirements([{}])

    assert credentials_satisfy(requirements, set())


def test_multiple_operations_are_detected():
    document = make_document(
        paths={
            "/users": {
                "get": {"responses": {}},
                "post": {"responses": {}},
            },
            "/orders": {
                "get": {"responses": {}},
            },
        }
    )

    operations = analyze_security(document).operations

    assert len(operations) == 3
    assert {(op.method, op.path) for op in operations} == {
        ("GET", "/users"),
        ("POST", "/users"),
        ("GET", "/orders"),
    }


@pytest.mark.parametrize(
    "security",
    [
        "BearerAuth",
        {"BearerAuth": []},
        [None],
        [["BearerAuth"]],
        [{"BearerAuth": "read"}],
        [{"BearerAuth": [123]}],
    ],
)
def test_invalid_security_requirements_are_rejected(security):
    with pytest.raises((TypeError, ValueError)):
        parse_requirements(security)


def test_invalid_components_are_rejected():
    document = make_document()
    document["components"] = []

    with pytest.raises(TypeError):
        analyze_security(document)


def test_invalid_security_schemes_are_rejected():
    document = make_document()
    document["components"]["securitySchemes"] = []

    with pytest.raises(TypeError):
        analyze_security(document)


def test_invalid_scheme_definition_is_rejected():
    document = make_document()
    document["components"]["securitySchemes"] = {"BearerAuth": "bearer"}

    with pytest.raises(TypeError):
        analyze_security(document)


def test_invalid_paths_are_rejected():
    document = make_document()
    document["paths"] = []

    with pytest.raises(TypeError):
        analyze_security(document)
