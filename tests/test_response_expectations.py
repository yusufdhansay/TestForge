from testforge.models import (
    GeneratedTestCase,
    ResponseExpectation,
    TestCategory,
)


def make_negative_case(**overrides):
    data = {
        "test_id": "TC-1000",
        "name": "POST /accounts - missing required name",
        "category": TestCategory.NEGATIVE,
        "method": "POST",
        "path": "/accounts",
        "request_body": {},
        "expected_status_codes": [],
    }
    data.update(overrides)
    return GeneratedTestCase(**data)


def test_negative_case_without_expectation():
    case = make_negative_case()

    assert case.expected_status_codes == []
    assert case.response_expectation is None


def test_negative_case_with_contract_expectation():
    case = make_negative_case(
        expected_status_codes=[422],
        response_expectation=ResponseExpectation(
            source="openapi",
            description="Validation error response",
        ),
    )

    assert case.expected_status_codes == [422]
    assert case.response_expectation.source == "openapi"


def test_negative_case_with_manual_expectation():
    case = make_negative_case(
        expected_status_codes=[400, 422],
        response_expectation=ResponseExpectation(
            source="manual",
            description="Approved validation status codes",
        ),
    )

    assert case.expected_status_codes == [400, 422]
    assert case.response_expectation.source == "manual"


def test_response_expectation_serialization():
    case = make_negative_case(
        expected_status_codes=[422],
        response_expectation=ResponseExpectation(
            source="openapi",
            description="Request validation failure",
        ),
    )

    serialized = case.model_dump(mode="json")

    assert serialized["response_expectation"]["source"] == "openapi"
    assert serialized["expected_status_codes"] == [422]
