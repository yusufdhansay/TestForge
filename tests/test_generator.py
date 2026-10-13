from testforge.generator import ContractTestGenerator
from testforge.models import TestCategory
from testforge.parser import OpenAPIParser


def test_generate_one_case_per_operation():
    specification = OpenAPIParser("examples/banking_api.json").parse()

    test_cases = ContractTestGenerator(specification).generate()

    positive_cases = [
        case for case in test_cases if case.category == TestCategory.POSITIVE
    ]

    assert len(positive_cases) == 3


def test_generated_cases_have_unique_ids():
    specification = OpenAPIParser("examples/banking_api.json").parse()

    test_cases = ContractTestGenerator(specification).generate()

    test_ids = [case.test_id for case in test_cases]

    assert len(test_ids) == len(set(test_ids))


def test_generated_cases_include_both_categories():
    specification = OpenAPIParser("examples/banking_api.json").parse()

    test_cases = ContractTestGenerator(specification).generate()

    categories = {case.category for case in test_cases}

    assert TestCategory.POSITIVE in categories
    assert TestCategory.NEGATIVE in categories


def test_extract_expected_success_status():
    specification = OpenAPIParser("examples/banking_api.json").parse()

    test_cases = ContractTestGenerator(specification).generate()

    post_case = next(case for case in test_cases if case.method == "POST")

    assert post_case.expected_status_codes == [201]


def test_generated_case_contains_operation_details():
    specification = OpenAPIParser("examples/banking_api.json").parse()

    test_cases = ContractTestGenerator(specification).generate()

    get_case = next(case for case in test_cases if case.path == "/accounts/{id}")

    assert get_case.method == "GET"
    assert get_case.category == TestCategory.POSITIVE
    assert get_case.test_id


def test_generate_path_parameter():
    specification = OpenAPIParser("examples/banking_api.json").parse()
    cases = ContractTestGenerator(specification).generate()

    case = next(c for c in cases if c.path == "/accounts/{id}")

    assert case.path_parameters["id"] == 0


def test_generate_json_request_body():
    specification = OpenAPIParser("examples/banking_api.json").parse()
    cases = ContractTestGenerator(specification).generate()

    case = next(c for c in cases if c.method == "POST")

    assert isinstance(case.request_body, dict)
    assert case.headers["Content-Type"] == "application/json"


def test_generate_seven_banking_cases():
    specification = OpenAPIParser("examples/banking_api.json").parse()

    cases = ContractTestGenerator(specification).generate()

    assert len(cases) == 7


def test_negative_cases_have_no_assumed_status():
    specification = OpenAPIParser("examples/banking_api.json").parse()

    cases = ContractTestGenerator(specification).generate()

    negative_cases = [case for case in cases if case.category == TestCategory.NEGATIVE]

    assert len(negative_cases) == 4
    assert all(case.expected_status_codes == [] for case in negative_cases)


def test_negative_cases_have_unique_ids():
    specification = OpenAPIParser("examples/banking_api.json").parse()

    cases = ContractTestGenerator(specification).generate()

    ids = [case.test_id for case in cases]

    assert len(ids) == len(set(ids))
