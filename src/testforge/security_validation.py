"""Validate configured credentials against OpenAPI security requirements."""

from testforge.security import SecurityAnalysis, SecurityScheme


def available_security_schemes(
    analysis: SecurityAnalysis,
    *,
    bearer_token: str | None,
    basic_username: str | None,
    api_key: str | None,
    api_key_name: str | None,
    api_key_location: str,
) -> set[str]:
    """Identify declared schemes supported by configured credentials."""
    available = set()

    for name, scheme in analysis.schemes.items():
        matches_bearer = scheme.kind == "bearer" and bearer_token is not None

        matches_basic = scheme.kind == "basic" and basic_username is not None

        matches_api_key = (
            scheme.kind == "apiKey"
            and api_key is not None
            and api_key_matches(
                scheme,
                api_key_name=api_key_name,
                api_key_location=api_key_location,
            )
        )

        if matches_bearer or matches_basic or matches_api_key:
            available.add(name)

    return available


def api_key_matches(
    scheme: SecurityScheme,
    *,
    api_key_name: str | None,
    api_key_location: str,
) -> bool:
    """Check that an API key matches the declared name and location."""
    if scheme.location != api_key_location:
        return False

    if scheme.parameter_name is None or api_key_name is None:
        return False

    if scheme.location == "header":
        return scheme.parameter_name.lower() == api_key_name.lower()

    return scheme.parameter_name == api_key_name


def validate_operation_security(
    analysis: SecurityAnalysis,
    *,
    bearer_token: str | None = None,
    basic_username: str | None = None,
    api_key: str | None = None,
    api_key_name: str | None = None,
    api_key_location: str = "header",
) -> None:
    """Reject operations whose declared security cannot be satisfied."""
    available = available_security_schemes(
        analysis,
        bearer_token=bearer_token,
        basic_username=basic_username,
        api_key=api_key,
        api_key_name=api_key_name,
        api_key_location=api_key_location,
    )

    for operation in analysis.operations:
        if operation.public:
            continue

        for requirement in operation.requirements:
            if all(name in available for name in requirement.schemes):
                break
        else:
            raise ValueError(
                "OpenAPI security requirements are not satisfied for "
                f"{operation.method} {operation.path}"
            )
