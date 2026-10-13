from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class APIParameter(BaseModel):
    name: str
    location: str
    required: bool = False
    schema_definition: dict[str, Any] = Field(default_factory=dict)


class APIOperation(BaseModel):
    method: str
    path: str
    summary: str = ""
    operation_id: str | None = None
    parameters: list[APIParameter] = Field(default_factory=list)
    request_body: dict[str, Any] | None = None
    responses: dict[str, Any] = Field(default_factory=dict)


class APISpecification(BaseModel):
    title: str
    version: str
    openapi_version: str
    operations: list[APIOperation] = Field(default_factory=list)


class TestCategory(str, Enum):
    __test__ = False

    POSITIVE = "positive"
    NEGATIVE = "negative"


class ResponseExpectation(BaseModel):
    """Describes why a response status is expected."""

    source: str
    description: str = ""


class GeneratedTestCase(BaseModel):
    test_id: str
    name: str
    category: TestCategory
    method: str
    path: str

    path_parameters: dict[str, Any] = Field(default_factory=dict)

    query_parameters: dict[str, Any] = Field(default_factory=dict)

    headers: dict[str, str] = Field(default_factory=dict)

    request_body: Any | None = None

    expected_status_codes: list[int] = Field(default_factory=list)

    response_expectation: ResponseExpectation | None = None
