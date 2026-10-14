import base64
import re
from time import perf_counter
from urllib.parse import quote, urlsplit

import httpx
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from testforge.execution_models import ExecutionResult, ExecutionStatus
from testforge.models import GeneratedTestCase
from testforge.schema_normalizer import normalize_openapi_schema

HTTP_TOKEN_PATTERN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
QUERY_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


def validate_bearer_token(token: str) -> str:
    """Validate a bearer token without exposing its value."""
    if not isinstance(token, str) or not token:
        raise ValueError("Bearer token must be a non-empty string")

    if not token.isascii() or any(
        character.isspace() or ord(character) < 33 or ord(character) == 127
        for character in token
    ):
        raise ValueError(
            "Bearer token must contain only non-whitespace ASCII characters"
        )

    return token


def validate_api_key(key: str) -> str:
    """Validate an API key without including its value in errors."""
    if not isinstance(key, str) or not key:
        raise ValueError("API key must be a non-empty string")

    if not key.isascii() or any(
        ord(character) < 33 or ord(character) > 126 for character in key
    ):
        raise ValueError(
            "API key must contain only printable, non-whitespace ASCII characters"
        )

    return key


def validate_api_key_configuration(
    api_key: str | None,
    api_key_name: str | None,
    api_key_location: str,
    bearer_token: str | None = None,
) -> tuple[str | None, str | None, str]:
    """Validate API key settings before constructing HTTP requests."""
    if api_key_location not in {"header", "query"}:
        raise ValueError("API key location must be 'header' or 'query'")

    if api_key is None:
        if api_key_name is not None:
            raise ValueError("API key name requires an API key")
        return None, None, api_key_location

    validated_key = validate_api_key(api_key)

    if api_key_name is None:
        api_key_name = "X-API-Key" if api_key_location == "header" else "api_key"

    if api_key_location == "header":
        if not HTTP_TOKEN_PATTERN.fullmatch(api_key_name):
            raise ValueError("Invalid API key header name")

        if api_key_name.lower() == "authorization" and bearer_token is not None:
            raise ValueError(
                "Bearer authentication and an Authorization API key conflict"
            )

    elif not QUERY_NAME_PATTERN.fullmatch(api_key_name):
        raise ValueError("Invalid API key query parameter name")

    return validated_key, api_key_name, api_key_location


def validate_basic_auth(
    username: str | None,
    password: str | None,
) -> tuple[str | None, str | None]:
    """Validate HTTP Basic credentials without exposing their values."""
    if username is None and password is None:
        return None, None

    if username is None or password is None:
        raise ValueError("Basic authentication requires both username and password")

    if not isinstance(username, str) or not isinstance(password, str):
        raise TypeError("Basic authentication credentials must be strings")

    if not username:
        raise ValueError("Basic authentication username must not be empty")

    if ":" in username:
        raise ValueError("Basic authentication username must not contain ':'")

    if any(ord(char) < 32 or ord(char) == 127 for char in username + password):
        raise ValueError(
            "Basic authentication credentials must not contain control characters"
        )

    try:
        username.encode("utf-8")
        password.encode("utf-8")
    except UnicodeError as error:
        raise ValueError(
            "Basic authentication credentials must be valid UTF-8"
        ) from error

    return username, password


def encode_basic_auth(username: str, password: str) -> str:
    """Encode validated credentials as an HTTP Basic Authorization value."""
    username, password = validate_basic_auth(username, password)
    credentials = f"{username}:{password}".encode()
    encoded = base64.b64encode(credentials).decode("ascii")
    return f"Basic {encoded}"


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
        bearer_token: str | None = None,
        api_key: str | None = None,
        api_key_name: str | None = None,
        api_key_location: str = "header",
        basic_username: str | None = None,
        basic_password: str | None = None,
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

        self.bearer_token = (
            validate_bearer_token(bearer_token) if bearer_token is not None else None
        )

        self.basic_username, self.basic_password = validate_basic_auth(
            basic_username,
            basic_password,
        )

        if self.bearer_token is not None and self.basic_username is not None:
            raise ValueError("Basic and Bearer authentication cannot be used together")

        (
            self.api_key,
            self.api_key_name,
            self.api_key_location,
        ) = validate_api_key_configuration(
            api_key,
            api_key_name,
            api_key_location,
            self.bearer_token,
        )

        if (
            self.basic_username is not None
            and self.api_key is not None
            and self.api_key_location == "header"
            and self.api_key_name.lower() == "authorization"
        ):
            raise ValueError(
                "Basic authentication and an Authorization API key conflict"
            )

        self.basic_auth_header = (
            encode_basic_auth(self.basic_username, self.basic_password)
            if self.basic_username is not None
            else None
        )

        self.client = httpx.Client(
            base_url=self.base_url,
            transport=transport,
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        )

    def _redact_error(self, message: str) -> str:
        """Remove configured credentials from execution error messages."""
        credentials = (
            getattr(self, "bearer_token", None),
            getattr(self, "api_key", None),
            getattr(self, "basic_auth_header", None),
            getattr(self, "basic_username", None),
            getattr(self, "basic_password", None),
        )

        # Redact longer credentials first to avoid partial replacements.
        for credential in sorted(
            (value for value in credentials if value),
            key=len,
            reverse=True,
        ):
            message = message.replace(credential, "[REDACTED]")

        return message

    def execute(self, test_case: GeneratedTestCase) -> ExecutionResult:
        """Execute one generated API contract test."""
        started = perf_counter()

        if (
            test_case.method.upper() not in {"GET", "HEAD", "OPTIONS"}
            and not self.allow_state_changes
        ):
            return ExecutionResult(
                test_id=test_case.test_id,
                status=ExecutionStatus.ERROR,
                expected_status_codes=test_case.expected_status_codes,
                error_message="State-changing HTTP methods require explicit approval",
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

            headers = dict(test_case.headers)
            query_parameters = dict(test_case.query_parameters)

            # getattr preserves compatibility with older mocked constructors.
            bearer_token = getattr(self, "bearer_token", None)
            basic_auth_header = getattr(self, "basic_auth_header", None)
            api_key = getattr(self, "api_key", None)
            api_key_name = getattr(self, "api_key_name", None)
            api_key_location = getattr(self, "api_key_location", "header")

            if bearer_token is not None or basic_auth_header is not None:
                headers = {
                    key: value
                    for key, value in headers.items()
                    if key.lower() != "authorization"
                }

                if bearer_token is not None:
                    headers["Authorization"] = f"Bearer {bearer_token}"
                else:
                    headers["Authorization"] = basic_auth_header

            if api_key is not None:
                if api_key_location == "header":
                    headers = {
                        key: value
                        for key, value in headers.items()
                        if key.lower() != api_key_name.lower()
                    }
                    headers[api_key_name] = api_key
                else:
                    query_parameters[api_key_name] = api_key

            response = self.client.request(
                method=test_case.method,
                url=path,
                params=query_parameters,
                headers=headers,
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
                                "expected application/json, "
                                f"received {content_type or 'missing'}"
                            )
                        else:
                            schema = normalize_openapi_schema(schema)
                            Draft202012Validator.check_schema(schema)

                            if (
                                response.status_code in {204, 205}
                                and not response.content
                            ):
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

            if (
                status == ExecutionStatus.PASSED
                and test_case.max_response_time_ms is not None
                and elapsed_ms > test_case.max_response_time_ms
            ):
                status = ExecutionStatus.FAILED
                error_message = (
                    "Response time exceeded threshold: "
                    f"{elapsed_ms:.2f} ms > "
                    f"{test_case.max_response_time_ms:.2f} ms"
                )

            return ExecutionResult(
                test_id=test_case.test_id,
                status=status,
                actual_status_code=response.status_code,
                expected_status_codes=test_case.expected_status_codes,
                response_time_ms=round(elapsed_ms, 2),
                error_message=(
                    self._redact_error(error_message)
                    if error_message is not None
                    else None
                ),
            )

        except (httpx.HTTPError, ValueError) as error:
            elapsed_ms = (perf_counter() - started) * 1000

            return ExecutionResult(
                test_id=test_case.test_id,
                status=ExecutionStatus.ERROR,
                expected_status_codes=test_case.expected_status_codes,
                response_time_ms=round(elapsed_ms, 2),
                error_message=self._redact_error(str(error)),
            )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
