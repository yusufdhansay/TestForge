from enum import Enum

from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    __test__ = False

    PASSED = "passed"
    FAILED = "failed"
    UNASSERTED = "unasserted"
    ERROR = "error"


class ExecutionResult(BaseModel):
    test_id: str
    status: ExecutionStatus

    actual_status_code: int | None = None
    expected_status_codes: list[int] = Field(default_factory=list)

    response_time_ms: float | None = None
    error_message: str | None = None
