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
