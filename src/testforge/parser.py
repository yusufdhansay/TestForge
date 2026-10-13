import json
from pathlib import Path
from typing import Any

import yaml

from testforge.models import (
    APIOperation,
    APIParameter,
    APISpecification,
)

HTTP_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
    "trace",
}


class OpenAPIParser:
    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)

    def load(self) -> dict[str, Any]:
        if not self.file_path.is_file():
            raise FileNotFoundError(f"Specification not found: {self.file_path}")

        suffix = self.file_path.suffix.lower()

        if suffix not in {".json", ".yaml", ".yml"}:
            raise ValueError("Unsupported file format. Use JSON or YAML.")

        content = self.file_path.read_text(encoding="utf-8")

        if suffix == ".json":
            data = json.loads(content)
        else:
            data = yaml.safe_load(content)

        if not isinstance(data, dict):
            raise TypeError("OpenAPI specification must be an object.")

        return data

    def parse(self) -> APISpecification:
        data = self.load()

        # Validate OpenAPI version
        if "openapi" not in data:
            raise ValueError("OpenAPI version is required.")

        openapi_version = data["openapi"]

        if not isinstance(openapi_version, str):
            raise TypeError("OpenAPI version must be a string.")

        if not openapi_version.startswith(("3.0.", "3.1.")):
            raise ValueError("Only OpenAPI 3.0 and 3.1 are supported.")

        # Validate API information
        if "info" not in data:
            raise ValueError("API info is required.")

        info = data["info"]

        if not isinstance(info, dict):
            raise TypeError("'info' must be an object.")

        if "title" not in info:
            raise ValueError("API title is required.")

        if not isinstance(info["title"], str):
            raise TypeError("API title must be a string.")

        if "version" not in info:
            raise ValueError("API version is required.")

        if not isinstance(info["version"], str):
            raise TypeError("API version must be a string.")

        # Validate paths
        paths = data.get("paths", {})

        if not isinstance(paths, dict):
            raise TypeError("'paths' must be an object.")

        operations: list[APIOperation] = []

        for path, path_item in paths.items():
            if not isinstance(path, str):
                raise TypeError("API path must be a string.")

            if not isinstance(path_item, dict):
                raise TypeError(f"Invalid path definition: {path}")

            path_parameters = path_item.get("parameters", [])

            if not isinstance(path_parameters, list):
                raise TypeError(f"Path parameters must be a list: {path}")

            for method, operation_data in path_item.items():
                if method not in HTTP_METHODS:
                    continue

                if not isinstance(operation_data, dict):
                    raise TypeError(f"Invalid operation: {method} {path}")

                operation_parameters = operation_data.get("parameters", [])

                if not isinstance(operation_parameters, list):
                    raise TypeError(
                        f"Operation parameters must be a list: {method.upper()} {path}"
                    )

                # Merge path-level and operation-level parameters.
                # Operation-level parameters take precedence.
                merged_parameters: dict[tuple[str, str], dict[str, Any]] = {}

                for parameter in path_parameters + operation_parameters:
                    if not isinstance(parameter, dict):
                        raise TypeError("Parameter definition must be an object.")

                    if "name" not in parameter:
                        raise ValueError("Parameter name is required.")

                    if "in" not in parameter:
                        raise ValueError("Parameter location is required.")

                    name = parameter["name"]
                    location = parameter["in"]

                    if not isinstance(name, str):
                        raise TypeError("Parameter name must be a string.")

                    if not isinstance(location, str):
                        raise TypeError("Parameter location must be a string.")

                    key = (name, location)
                    merged_parameters[key] = parameter

                parameters = [
                    APIParameter(
                        name=parameter["name"],
                        location=parameter["in"],
                        required=parameter.get("required", False),
                        schema_definition=parameter.get("schema", {}),
                    )
                    for parameter in merged_parameters.values()
                ]

                operations.append(
                    APIOperation(
                        method=method.upper(),
                        path=path,
                        summary=operation_data.get("summary", ""),
                        operation_id=operation_data.get("operationId"),
                        parameters=parameters,
                        request_body=operation_data.get("requestBody"),
                        responses=operation_data.get("responses", {}),
                    )
                )

        return APISpecification(
            title=info["title"],
            version=info["version"],
            openapi_version=openapi_version,
            operations=operations,
        )
