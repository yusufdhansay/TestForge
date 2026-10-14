from time import perf_counter
from urllib.parse import quote, urlsplit

import httpx
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from testforge.execution_models import ExecutionResult, ExecutionStatus
from testforge.models import GeneratedTestCase
from testforge.schema_normalizer import normalize_openapi_schema


class HTTPTestExecutor:
    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
        allow_network: bool = False,
        approved_origins: set[str] | None = None,
        allow_state_changes: bool = False,
    ):
        if timeout <= 0:
            raise ValueError("Timeout must be positive")

        parsed = urlsplit(base_url)

        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Invalid base URL")

        origin = f"{parsed.scheme}://{parsed.netloc}"

        if transport is None:
            if not allow_network:
                raise ValueError(
                    "Network access is disabled. "
                    "Provide a mock transport or explicitly enable network access."
                )

            if not approved_origins or origin not in approved_origins:
                raise ValueError(f"Target origin is not approved: {origin}")

        self.base_url = base_url.rstrip("/")
        self.allow_state_changes = allow_state_changes
        self.client = httpx.Client(
            base_url=self.base_url,
            transport=transport,
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        )

    def execute(self, test_case: GeneratedTestCase) -> ExecutionResult:
        started = perf_counter()

        if (
            test_case.method.upper() not in {"GET", "HEAD", "OPTIONS"}
            and not self.allow_state_changes
        ):
            return ExecutionResult(
                test_id=test_case.test_id,
                status=ExecutionStatus.ERROR,
                expected_status_codes=test_case.expected_status_codes,
                error_message=("State-changing HTTP methods require explicit approval"),
            )

        try:
            path = test_case.path

            for name, value in test_case.path_parameters.items():
                path = path.replace(
                    "{" + name + "}",
                    quote(str(value), safe=""),
                )

            if "{" in path or "}" in path:
                raise ValueError(f"Unresolved path parameters in {path}")

            parsed_path = urlsplit(path)

            if (
                not path.startswith("/")
                or path.startswith("//")
                or parsed_path.scheme
                or parsed_path.netloc
                or parsed_path.query
                or parsed_path.fragment
                or "\\" in path
            ):
                raise ValueError(f"Unsafe API path: {path}")

            response = self.client.request(
                method=test_case.method,
                url=path,
                params=test_case.query_parameters,
                headers=test_case.headers,
                json=test_case.request_body,
            )

            elapsed_ms = (perf_counter() - started) * 1000

            if not test_case.expected_status_codes:
                status = ExecutionStatus.UNASSERTED
            elif response.status_code in test_case.expected_status_codes:
                status = ExecutionStatus.PASSED
            else:
                status = ExecutionStatus.FAILED

            error_message = None

            if status == ExecutionStatus.PASSED:
                schema = test_case.response_schemas.get(response.status_code)

                if schema is not None:
                    try:
                        content_type = response.headers.get("Content-Type", "")
                        media_type = content_type.split(";", 1)[0].strip().lower()

                        if media_type != "application/json":
                            status = ExecutionStatus.FAILED
                            error_message = (
                                "Response Content-Type mismatch: "
                                f"expected application/json, received {content_type or 'missing'}"
                            )
                        else:
                            schema = normalize_openapi_schema(schema)
                            Draft202012Validator.check_schema(schema)

                            response_data = response.json()
                            Draft202012Validator(schema).validate(response_data)
                            Draft202012Validator.check_schema(schema)

                        if response.status_code in {204, 205} and not response.content:
                            # Empty responses are valid only when no body is expected.
                            raise ValueError(
                                "Response body missing for declared JSON schema"
                            )

                        response_data = response.json()
                        Draft202012Validator(schema).validate(response_data)

                    except ValidationError as error:
                        status = ExecutionStatus.FAILED
                        error_message = (
                            f"Response schema validation failed: {error.message}"
                        )

                    except (ValueError, httpx.DecodingError) as error:
                        status = ExecutionStatus.FAILED
                        error_message = f"Invalid JSON response: {error}"

                    except SchemaError as error:
                        status = ExecutionStatus.ERROR
                        error_message = f"Invalid response schema: {error.message}"

            return ExecutionResult(
                test_id=test_case.test_id,
                status=status,
                actual_status_code=response.status_code,
                expected_status_codes=test_case.expected_status_codes,
                response_time_ms=round(elapsed_ms, 2),
                error_message=error_message,
            )

        except (httpx.HTTPError, ValueError) as error:
            elapsed_ms = (perf_counter() - started) * 1000

            return ExecutionResult(
                test_id=test_case.test_id,
                status=ExecutionStatus.ERROR,
                expected_status_codes=test_case.expected_status_codes,
                response_time_ms=round(elapsed_ms, 2),
                error_message=str(error),
            )

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
