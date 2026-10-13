from typing import Any

from testforge.models import ResponseExpectation


def extract_negative_expectation(
    responses: dict[str, Any],
) -> tuple[list[int], ResponseExpectation | None]:
    """Extract an unambiguous documented client-error response."""

    client_error_codes = sorted(
        {int(code) for code in responses if code.isdigit() and 400 <= int(code) < 500}
    )

    validation_status_codes = {400, 422}

    if (
        len(client_error_codes) != 1
        or client_error_codes[0] not in validation_status_codes
    ):
        return [], None

    status_code = client_error_codes[0]
    response = responses.get(str(status_code), {})

    description = ""
    if isinstance(response, dict):
        description = str(response.get("description", ""))

    return [status_code], ResponseExpectation(
        source="openapi",
        description=description,
    )
