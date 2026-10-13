from testforge.response_expectations import extract_negative_expectation


def test_extract_single_documented_validation_status():
    codes, expectation = extract_negative_expectation(
        {"201": {}, "422": {"description": "Validation error"}}
    )

    assert codes == [422]
    assert expectation is not None
    assert expectation.source == "openapi"
    assert expectation.description == "Validation error"


def test_no_documented_client_error():
    codes, expectation = extract_negative_expectation({"200": {}, "500": {}})

    assert codes == []
    assert expectation is None


def test_multiple_client_error_codes_remain_unasserted():
    codes, expectation = extract_negative_expectation({"400": {}, "404": {}, "422": {}})

    assert codes == []
    assert expectation is None


def test_default_response_is_not_assumed():
    codes, expectation = extract_negative_expectation(
        {"201": {}, "default": {"description": "Error"}}
    )

    assert codes == []
    assert expectation is None


def test_wildcard_response_is_not_assumed():
    codes, expectation = extract_negative_expectation(
        {"201": {}, "4XX": {"description": "Client error"}}
    )

    assert codes == []
    assert expectation is None


def test_not_found_response_is_not_assumed_for_body_validation():
    codes, expectation = extract_negative_expectation(
        {"200": {}, "404": {"description": "Not found"}}
    )

    assert codes == []
    assert expectation is None


def test_authentication_error_is_not_assumed_for_body_validation():
    codes, expectation = extract_negative_expectation(
        {"200": {}, "401": {"description": "Unauthorized"}}
    )

    assert codes == []
    assert expectation is None


def test_bad_request_is_accepted_as_validation_expectation():
    codes, expectation = extract_negative_expectation(
        {"201": {}, "400": {"description": "Invalid request body"}}
    )

    assert codes == [400]
    assert expectation is not None
    assert expectation.source == "openapi"
