"""Select authentication credentials for individual OpenAPI operations."""

from dataclasses import dataclass

from testforge.security import SecurityAnalysis
from testforge.security_validation import available_security_schemes


@dataclass(frozen=True)
class OperationAuth:
    """Authentication methods enabled for one operation."""

    bearer: bool = False
    basic: bool = False
    api_key: bool = False


def build_operation_auth(
    analysis: SecurityAnalysis,
    *,
    bearer_token: str | None = None,
    basic_username: str | None = None,
    api_key: str | None = None,
    api_key_name: str | None = None,
    api_key_location: str = "header",
) -> dict[tuple[str, str], OperationAuth]:
    """Select one satisfiable security alternative per operation.

    Public operations receive no configured credentials. Protected
    operations receive only the methods required by the selected
    alternative.

    Raises ValueError before execution when requirements cannot
    be satisfied.
    """
    available = available_security_schemes(
        analysis,
        bearer_token=bearer_token,
        basic_username=basic_username,
        api_key=api_key,
        api_key_name=api_key_name,
        api_key_location=api_key_location,
    )

    routing = {}

    for operation in analysis.operations:
        key = (operation.method.upper(), operation.path)

        if operation.public:
            routing[key] = OperationAuth()
            continue

        selected = None

        for requirement in operation.requirements:
            if all(name in available for name in requirement.schemes):
                selected = requirement
                break

        if selected is None:
            raise ValueError(
                "OpenAPI security requirements are not satisfied for "
                f"{operation.method} {operation.path}"
            )

        kinds = {analysis.schemes[name].kind for name in selected.schemes}

        routing[key] = OperationAuth(
            bearer="bearer" in kinds,
            basic="basic" in kinds,
            api_key="apiKey" in kinds,
        )

    return routing
