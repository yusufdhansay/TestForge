"""Authentication security reporting and quality-gate evaluation."""

import json
from dataclasses import dataclass
from pathlib import Path

from testforge.execution_models import ExecutionResult, ExecutionStatus
from testforge.models import GeneratedTestCase


@dataclass(frozen=True)
class AuthSummary:
    generated: int
    executed: int
    passed: int
    failed: int
    errors: int
    unasserted: int
    pass_rate: float

    def to_dict(self) -> dict:
        return {
            "generated": self.generated,
            "executed": self.executed,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "unasserted": self.unasserted,
            "pass_rate": self.pass_rate,
        }


def summarize_auth_results(
    cases: list[GeneratedTestCase],
    results: list[ExecutionResult],
) -> AuthSummary:
    """Summarize authentication checks independently of contract tests."""
    generated = len(cases)
    executed = sum(result.actual_status_code is not None for result in results)

    passed = sum(result.status == ExecutionStatus.PASSED for result in results)
    failed = sum(result.status == ExecutionStatus.FAILED for result in results)
    errors = sum(result.status == ExecutionStatus.ERROR for result in results)
    unasserted = sum(result.status == ExecutionStatus.UNASSERTED for result in results)

    pass_rate = round(passed / generated * 100, 2) if generated else 0.0

    return AuthSummary(
        generated=generated,
        executed=executed,
        passed=passed,
        failed=failed,
        errors=errors,
        unasserted=unasserted,
        pass_rate=pass_rate,
    )


def evaluate_auth_gate(
    summary: AuthSummary,
    minimum_pass_rate: float | None,
) -> list[str]:
    """Return actionable CI failures for authentication testing."""
    if minimum_pass_rate is None:
        return []

    if summary.generated == 0:
        return [
            (
                "Authentication quality gate cannot pass: "
                "no authentication tests were generated."
            )
        ]

    if summary.pass_rate < minimum_pass_rate:
        return [
            (
                f"Authentication pass rate {summary.pass_rate:.2f}% "
                f"is below the required {minimum_pass_rate:.2f}%."
            )
        ]

    return []


def export_auth_report(
    destination: Path,
    cases: list[GeneratedTestCase],
    results: list[ExecutionResult],
    summary: AuthSummary,
) -> None:
    """Export authentication results without storing credentials."""
    cases_by_id = {case.test_id: case for case in cases}

    checks = []

    for result in results:
        case = cases_by_id.get(result.test_id)

        if case is None:
            continue

        checks.append(
            {
                "test_id": result.test_id,
                "name": case.name,
                "method": case.method,
                "path": case.path,
                "status": result.status.value,
                "expected_status_codes": result.expected_status_codes,
                "actual_status_code": result.actual_status_code,
                "response_time_ms": result.response_time_ms,
            }
        )

    payload = {
        "report_type": "authentication_security",
        "summary": summary.to_dict(),
        "checks": checks,
    }

    destination.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
