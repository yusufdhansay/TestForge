"""OpenAPI 3.x security scheme detection and requirement matching."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SecurityScheme:
    name: str
    kind: str
    location: str | None = None
    parameter_name: str | None = None


@dataclass(frozen=True)
class SecurityRequirement:
    """One OpenAPI security requirement object.

    Multiple schemes within an object are AND requirements.
    Multiple requirement objects are OR alternatives.
    """

    schemes: tuple[str, ...]


@dataclass(frozen=True)
class OperationSecurity:
    method: str
    path: str
    requirements: tuple[SecurityRequirement, ...]
    public: bool


@dataclass(frozen=True)
class SecurityAnalysis:
    schemes: dict[str, SecurityScheme]
    operations: tuple[OperationSecurity, ...]


SUPPORTED_HTTP_SCHEMES = {"basic", "bearer"}
HTTP_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
    "trace",
}


def detect_security_scheme(
    name: str,
    definition: dict[str, Any],
) -> SecurityScheme:
    """Classify a declared OpenAPI security scheme."""
    scheme_type = definition.get("type")

    if scheme_type == "http":
        http_scheme = definition.get("scheme")

        if isinstance(http_scheme, str):
            http_scheme = http_scheme.lower()

        if http_scheme in SUPPORTED_HTTP_SCHEMES:
            return SecurityScheme(name=name, kind=http_scheme)

        return SecurityScheme(name=name, kind="unsupported")

    if scheme_type == "apiKey":
        location = definition.get("in")
        parameter_name = definition.get("name")

        if (
            location in {"header", "query"}
            and isinstance(parameter_name, str)
            and parameter_name
        ):
            return SecurityScheme(
                name=name,
                kind="apiKey",
                location=location,
                parameter_name=parameter_name,
            )

        return SecurityScheme(name=name, kind="unsupported")

    return SecurityScheme(name=name, kind="unsupported")


def parse_requirements(
    value: Any,
) -> tuple[SecurityRequirement, ...]:
    """Parse OpenAPI security requirements while preserving OR/AND semantics."""
    if not isinstance(value, list):
        raise TypeError("OpenAPI security requirements must be a list")

    requirements = []

    for entry in value:
        if not isinstance(entry, dict):
            raise TypeError("Each security requirement must be an object")

        for scopes in entry.values():
            if not isinstance(scopes, list) or not all(
                isinstance(scope, str) for scope in scopes
            ):
                raise ValueError("Security requirement scopes must be string lists")

        requirements.append(SecurityRequirement(schemes=tuple(entry.keys())))

    return tuple(requirements)


def analyze_security(document: dict[str, Any]) -> SecurityAnalysis:
    """Analyze global and operation-level OpenAPI security declarations."""
    components = document.get("components", {})

    if not isinstance(components, dict):
        raise TypeError("OpenAPI components must be an object")

    definitions = components.get("securitySchemes", {})

    if not isinstance(definitions, dict):
        raise TypeError("OpenAPI securitySchemes must be an object")

    schemes = {}

    for name, definition in definitions.items():
        if not isinstance(name, str) or not isinstance(definition, dict):
            raise TypeError("Invalid OpenAPI security scheme definition")

        schemes[name] = detect_security_scheme(name, definition)

    global_requirements = parse_requirements(document.get("security", []))
    paths = document.get("paths", {})

    if not isinstance(paths, dict):
        raise TypeError("OpenAPI paths must be an object")

    operations = []

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue

            if not isinstance(operation, dict):
                continue

            requirements = (
                parse_requirements(operation["security"])
                if "security" in operation
                else global_requirements
            )

            # No requirements, or an empty requirement object,
            # means anonymous access is permitted.
            public = not requirements or any(
                not requirement.schemes for requirement in requirements
            )

            operations.append(
                OperationSecurity(
                    method=method.upper(),
                    path=path,
                    requirements=requirements,
                    public=public,
                )
            )

    return SecurityAnalysis(
        schemes=schemes,
        operations=tuple(operations),
    )


def credentials_satisfy(
    requirements: tuple[SecurityRequirement, ...],
    available_schemes: set[str],
) -> bool:
    """Return whether supplied scheme names satisfy an OpenAPI requirement.

    Each requirement object is an AND group; the groups are OR alternatives.
    """
    if not requirements:
        return True

    return any(
        set(requirement.schemes).issubset(available_schemes)
        for requirement in requirements
    )
