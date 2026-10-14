"""Generate opt-in negative authentication scenarios from OpenAPI security routing.

Scenarios describe intended credential mutations. They do not execute HTTP
requests, read secrets, or change normal contract-test generation.
"""

from dataclasses import dataclass
from enum import Enum

from testforge.security import SecurityAnalysis
from testforge.security_routing import OperationAuth


class AuthMutation(str, Enum):
    MISSING = "missing"
    INVALID = "invalid"
    MALFORMED = "malformed"


@dataclass(frozen=True)
class AuthTestScenario:
    method: str
    path: str
    mutation: AuthMutation
    auth_kind: str
    expected_status_codes: tuple[int, ...]
    name: str


def generate_auth_scenarios(
    analysis: SecurityAnalysis,
    operation_auth: dict[tuple[str, str], OperationAuth],
) -> list[AuthTestScenario]:
    """Create scenarios for protected operations with selected credentials.

    401 is the default expected response for missing/invalid authentication.
    If an operation explicitly documents 401, the same expectation applies.
    A 403 authorization test requires a separate low-privilege identity and
    is deliberately not generated here.

    For AND requirements, test each selected credential independently.
    For OR requirements, the supplied operation_auth must already contain
    the chosen satisfiable alternative from Phase 10D.
    """
    scenarios: list[AuthTestScenario] = []
    for operation in analysis.operations:
        if operation.public:
            continue
        key = (operation.method.upper(), operation.path)
        if key not in operation_auth:
            raise ValueError(
                f"Missing authentication routing for {operation.method} {operation.path}"
            )
        selected = operation_auth[key]
        kinds = (
            ("bearer", selected.bearer),
            ("basic", selected.basic),
            ("api_key", selected.api_key),
        )
        if not any(enabled for _, enabled in kinds):
            raise ValueError(
                f"No authentication method selected for {operation.method} {operation.path}"
            )
        for kind, enabled in kinds:
            if not enabled:
                continue
            mutations = [AuthMutation.MISSING, AuthMutation.INVALID]
            if kind in {"bearer", "basic"}:
                mutations.append(AuthMutation.MALFORMED)
            for mutation in mutations:
                scenarios.append(
                    AuthTestScenario(
                        method=operation.method.upper(),
                        path=operation.path,
                        mutation=mutation,
                        auth_kind=kind,
                        expected_status_codes=(401,),
                        name=(
                            f"{operation.method.upper()} {operation.path} - "
                            f"{kind} {mutation.value} credentials"
                        ),
                    )
                )
    return scenarios
