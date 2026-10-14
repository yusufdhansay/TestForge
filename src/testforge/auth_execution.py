"""Build isolated HTTP test cases for opt-in negative authentication testing."""

from testforge.auth_generator import AuthMutation, AuthTestScenario
from testforge.models import GeneratedTestCase, TestCategory
from testforge.security import SecurityAnalysis

# Fixed, non-secret test values. Never reuse configured authentication secrets.
INVALID_CREDENTIAL = "testforge-invalid-credential"


def build_auth_test_cases(
    scenarios: list[AuthTestScenario],
    contract_tests: list[GeneratedTestCase],
    analysis: SecurityAnalysis,
) -> list[GeneratedTestCase]:
    """Create requests for isolated execution by an uncredentialed HTTP executor.

    For AND requirements, each mutation deliberately omits all other credentials.
    These cases prove rejection of an unauthenticated/invalid request, not
    independent enforcement of each component of an AND requirement.
    """
    base_cases = {}
    for case in contract_tests:
        if case.category == TestCategory.POSITIVE:
            base_cases.setdefault((case.method.upper(), case.path), case)

    auth_headers = {"authorization"}
    auth_query_names = set()
    api_key_schemes = []
    for scheme in analysis.schemes.values():
        if scheme.kind != "apiKey" or not scheme.parameter_name:
            continue
        api_key_schemes.append(scheme)
        if scheme.location == "header":
            auth_headers.add(scheme.parameter_name.lower())
        elif scheme.location == "query":
            auth_query_names.add(scheme.parameter_name)

    output = []
    for number, scenario in enumerate(scenarios, 1):
        key = (scenario.method.upper(), scenario.path)
        if key not in base_cases:
            raise ValueError(
                f"No positive contract test for {scenario.method} {scenario.path}"
            )

        base = base_cases[key]
        headers = {
            name: value
            for name, value in base.headers.items()
            if name.lower() not in auth_headers
        }
        query = {
            name: value
            for name, value in base.query_parameters.items()
            if name not in auth_query_names
        }

        if scenario.mutation != AuthMutation.MISSING:
            if scenario.auth_kind == "bearer":
                value = (
                    f"Bearer {INVALID_CREDENTIAL}"
                    if scenario.mutation == AuthMutation.INVALID
                    else "Bearer"
                )
                headers["Authorization"] = value
            elif scenario.auth_kind == "basic":
                headers["Authorization"] = (
                    "Basic dGVzdGZvcmdlOmludmFsaWQ="
                    if scenario.mutation == AuthMutation.INVALID
                    else "Basic !!!"
                )
            elif scenario.auth_kind == "api_key":
                operation = next(
                    (
                        item
                        for item in analysis.operations
                        if (item.method, item.path) == key
                    ),
                    None,
                )
                if operation is None:
                    raise ValueError(
                        f"Missing security analysis for {scenario.method} {scenario.path}"
                    )
                declared = {
                    name
                    for requirement in operation.requirements
                    for name in requirement.schemes
                }
                matching = [
                    scheme for scheme in api_key_schemes if scheme.name in declared
                ]
                if len(matching) != 1:
                    raise ValueError(
                        "API key negative testing requires exactly one applicable "
                        f"API key scheme for {scenario.method} {scenario.path}"
                    )
                scheme = matching[0]
                if scheme.location == "header":
                    headers[scheme.parameter_name] = INVALID_CREDENTIAL
                else:
                    query[scheme.parameter_name] = INVALID_CREDENTIAL
            else:
                raise ValueError(
                    f"Unsupported authentication kind: {scenario.auth_kind}"
                )

        output.append(
            base.model_copy(
                update={
                    "test_id": f"AUTH-{number:04d}",
                    "name": scenario.name,
                    "category": TestCategory.NEGATIVE,
                    "headers": headers,
                    "query_parameters": query,
                    "expected_status_codes": list(scenario.expected_status_codes),
                    "response_schemas": {},
                    "response_expectation": None,
                },
                deep=True,
            )
        )
    return output
