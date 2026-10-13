from pydantic import BaseModel, Field


class ExecutionSummary(BaseModel):
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    unasserted: int = Field(ge=0)
    errors: int = Field(ge=0)

    pass_rate: float = Field(ge=0, le=100)

    average_response_time_ms: float | None = Field(default=None, ge=0)
    min_response_time_ms: float | None = Field(default=None, ge=0)
    max_response_time_ms: float | None = Field(default=None, ge=0)
    p95_response_time_ms: float | None = Field(default=None, ge=0)
