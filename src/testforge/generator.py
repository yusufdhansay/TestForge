from testforge.models import (
    APISpecification,
    GeneratedTestCase,
    TestCategory,
)
from testforge.negative_generator import generate_negative_bodies
from testforge.response_expectations import extract_negative_expectation
from testforge.schema_generator import generate_value


class ContractTestGenerator:
    def __init__(self, specification: APISpecification):
        self.specification = specification

    def generate(self) -> list[GeneratedTestCase]:
        test_cases = []
        test_number = 1

        for operation in self.specification.operations:
            success_status_codes = [
                int(code)
                for code in operation.responses
                if code.isdigit() and 200 <= int(code) < 300
            ]

            path_parameters = {}
            query_parameters = {}
            headers = {}

            for parameter in operation.parameters:
                if not parameter.required:
                    continue

                value = generate_value(parameter.schema_definition)

                if parameter.location == "path":
                    path_parameters[parameter.name] = value
                elif parameter.location == "query":
                    query_parameters[parameter.name] = value
                elif parameter.location == "header":
                    headers[parameter.name] = str(value)

            request_body = None
            body_schema = None

            if operation.request_body:
                content = operation.request_body.get("content", {})
                json_media_type = content.get("application/json")

                if json_media_type:
                    body_schema = json_media_type.get("schema")

                    if body_schema:
                        request_body = generate_value(body_schema)
                        headers["Content-Type"] = "application/json"

            test_cases.append(
                GeneratedTestCase(
                    test_id=f"TC-{test_number:04d}",
                    name=f"{operation.method} {operation.path} - positive test",
                    category=TestCategory.POSITIVE,
                    method=operation.method,
                    path=operation.path,
                    path_parameters=path_parameters.copy(),
                    query_parameters=query_parameters.copy(),
                    headers=headers.copy(),
                    request_body=request_body,
                    expected_status_codes=success_status_codes,
                )
            )
            test_number += 1

            negative_status_codes, negative_expectation = extract_negative_expectation(
                operation.responses
            )

            if body_schema and body_schema.get("type") == "object":
                negative_bodies = generate_negative_bodies(body_schema)

                for mutation_name, invalid_body in negative_bodies:
                    test_cases.append(
                        GeneratedTestCase(
                            test_id=f"TC-{test_number:04d}",
                            name=(
                                f"{operation.method} {operation.path} - {mutation_name}"
                            ),
                            category=TestCategory.NEGATIVE,
                            method=operation.method,
                            path=operation.path,
                            path_parameters=path_parameters.copy(),
                            query_parameters=query_parameters.copy(),
                            headers=headers.copy(),
                            request_body=invalid_body,
                            expected_status_codes=negative_status_codes.copy(),
                            response_expectation=negative_expectation,
                        )
                    )
                    test_number += 1

        return test_cases
