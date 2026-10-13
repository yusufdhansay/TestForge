import json

import httpx

from testforge.execution_models import ExecutionStatus
from testforge.executor import HTTPTestExecutor
from testforge.generator import ContractTestGenerator
from testforge.models import TestCategory
from testforge.parser import OpenAPIParser


def banking_api_handler(request: httpx.Request) -> httpx.Response:
    """Simulate a banking API without network access."""

    if request.method == "GET" and request.url.path == "/accounts":
        return httpx.Response(200, json={"accounts": []})

    if request.method == "GET" and request.url.path == "/accounts/0":
        return httpx.Response(
            200,
            json={"id": 0, "name": "test-account", "balance": 0},
        )

    if request.method == "POST" and request.url.path == "/accounts":
        try:
            body = json.loads(request.content)
        except (ValueError, TypeError):
            return httpx.Response(400)

        if not isinstance(body, dict):
            return httpx.Response(422)

        if (
            not isinstance(body.get("name"), str)
            or not isinstance(body.get("balance"), (int, float))
            or isinstance(body.get("balance"), bool)
        ):
            return httpx.Response(422)

        return httpx.Response(201, json={"id": 1})

    return httpx.Response(404)


def test_complete_banking_pipeline():
    specification = OpenAPIParser("examples/banking_api.json").parse()

    test_cases = ContractTestGenerator(specification).generate()

    assert len(test_cases) == 7

    transport = httpx.MockTransport(banking_api_handler)

    with HTTPTestExecutor(
        "https://banking.test",
        transport=transport,
        allow_state_changes=True,
    ) as executor:
        results = [executor.execute(case) for case in test_cases]

    assert len(results) == 7

    positive_results = [
        result
        for case, result in zip(test_cases, results)
        if case.category == TestCategory.POSITIVE
    ]

    negative_results = [
        result
        for case, result in zip(test_cases, results)
        if case.category == TestCategory.NEGATIVE
    ]

    assert len(positive_results) == 3
    assert len(negative_results) == 4

    assert all(result.status == ExecutionStatus.PASSED for result in positive_results)

    assert all(
        result.status == ExecutionStatus.UNASSERTED for result in negative_results
    )

    assert all(result.actual_status_code == 422 for result in negative_results)
