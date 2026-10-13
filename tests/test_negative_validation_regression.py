import httpx

from testforge.execution_models import ExecutionStatus
from testforge.executor import HTTPTestExecutor
from testforge.generator import ContractTestGenerator
from testforge.models import TestCategory
from testforge.parser import OpenAPIParser
from testforge.reporter import ExecutionReporter


def test_api_accepting_invalid_input_is_detected():
    specification = OpenAPIParser("examples/banking_api.json").parse()

    post_operation = next(
        operation
        for operation in specification.operations
        if operation.method.upper() == "POST" and operation.path == "/accounts"
    )

    post_operation.responses["422"] = {"description": "Request validation failed"}

    test_cases = ContractTestGenerator(specification).generate()

    invalid_case = next(
        case
        for case in test_cases
        if case.category == TestCategory.NEGATIVE
        and "missing_required_name" in case.name
    )

    assert invalid_case.expected_status_codes == [422]
    assert "name" not in invalid_case.request_body

    # Simulate a defective API that accepts an invalid request.
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            201,
            json={"id": "acc-001"},
        )
    )

    with HTTPTestExecutor(
        base_url="https://banking.test",
        transport=transport,
        allow_state_changes=True,
    ) as executor:
        result = executor.execute(invalid_case)

    assert result.status == ExecutionStatus.FAILED
    assert result.actual_status_code == 201
    assert result.expected_status_codes == [422]

    summary = ExecutionReporter().summarize([result])

    assert summary.total == 1
    assert summary.passed == 0
    assert summary.failed == 1
    assert summary.unasserted == 0
    assert summary.errors == 0
    assert summary.pass_rate == 0.0
