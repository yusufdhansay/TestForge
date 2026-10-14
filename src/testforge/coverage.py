from collections import Counter

from pydantic import BaseModel, Field

from testforge.execution_models import ExecutionResult
from testforge.models import APISpecification, GeneratedTestCase


class OperationCoverage(BaseModel):
    method: str
    path: str
    generated_tests: int = 0
    executed_tests: int = 0
    is_generated: bool = False
    is_executed: bool = False


class MethodCoverage(BaseModel):
    method: str
    total_operations: int
    generated_operations: int
    executed_operations: int
    generated_coverage_percent: float
    executed_coverage_percent: float


class CoverageReport(BaseModel):
    total_operations: int = 0
    generated_operations: int = 0
    executed_operations: int = 0

    generated_coverage_percent: float = 0.0
    executed_coverage_percent: float = 0.0

    total_generated_tests: int = 0
    total_executed_tests: int = 0

    operations: list[OperationCoverage] = Field(default_factory=list)
    methods: list[MethodCoverage] = Field(default_factory=list)
    untested_operations: list[str] = Field(default_factory=list)


class ContractCoverageAnalyzer:
    """Analyze generated and executed OpenAPI operation coverage."""

    @staticmethod
    def _operation_key(method: str, path: str) -> tuple[str, str]:
        return method.upper(), path

    @staticmethod
    def _percentage(covered: int, total: int) -> float:
        if total == 0:
            return 0.0

        return round(covered / total * 100, 2)

    def analyze(
        self,
        specification: APISpecification,
        test_cases: list[GeneratedTestCase],
        results: list[ExecutionResult] | None = None,
    ) -> CoverageReport:
        results = results or []

        # Each generated test belongs to one OpenAPI operation.
        generated_counts = Counter(
            self._operation_key(test_case.method, test_case.path)
            for test_case in test_cases
        )

        # Match execution results to generated tests using test IDs.
        tests_by_id = {test_case.test_id: test_case for test_case in test_cases}

        executed_counts = Counter()
        total_executed_tests = 0

        for result in results:
            test_case = tests_by_id.get(result.test_id)

            if test_case is None:
                continue

            # A response status code indicates that an HTTP response
            # was received, even if contract assertions failed.
            #
            # Requests blocked before execution and transport failures
            # without an HTTP response do not count as executed here.
            if result.actual_status_code is None:
                continue

            key = self._operation_key(
                test_case.method,
                test_case.path,
            )

            executed_counts[key] += 1
            total_executed_tests += 1

        operations = []
        method_totals = Counter()
        method_generated = Counter()
        method_executed = Counter()

        seen_operations = set()

        for operation in specification.operations:
            key = self._operation_key(
                operation.method,
                operation.path,
            )

            # Prevent duplicate operation entries from inflating coverage.
            if key in seen_operations:
                continue

            seen_operations.add(key)

            method, path = key

            generated_tests = generated_counts[key]
            executed_tests = executed_counts[key]

            is_generated = generated_tests > 0
            is_executed = executed_tests > 0

            operations.append(
                OperationCoverage(
                    method=method,
                    path=path,
                    generated_tests=generated_tests,
                    executed_tests=executed_tests,
                    is_generated=is_generated,
                    is_executed=is_executed,
                )
            )

            method_totals[method] += 1

            if is_generated:
                method_generated[method] += 1

            if is_executed:
                method_executed[method] += 1

        total_operations = len(operations)

        generated_operations = sum(operation.is_generated for operation in operations)

        executed_operations = sum(operation.is_executed for operation in operations)

        methods = []

        for method in sorted(method_totals):
            total = method_totals[method]
            generated = method_generated[method]
            executed = method_executed[method]

            methods.append(
                MethodCoverage(
                    method=method,
                    total_operations=total,
                    generated_operations=generated,
                    executed_operations=executed,
                    generated_coverage_percent=self._percentage(
                        generated,
                        total,
                    ),
                    executed_coverage_percent=self._percentage(
                        executed,
                        total,
                    ),
                )
            )

        untested_operations = [
            f"{operation.method} {operation.path}"
            for operation in operations
            if not operation.is_executed
        ]

        return CoverageReport(
            total_operations=total_operations,
            generated_operations=generated_operations,
            executed_operations=executed_operations,
            generated_coverage_percent=self._percentage(
                generated_operations,
                total_operations,
            ),
            executed_coverage_percent=self._percentage(
                executed_operations,
                total_operations,
            ),
            total_generated_tests=len(test_cases),
            total_executed_tests=total_executed_tests,
            operations=operations,
            methods=methods,
            untested_operations=untested_operations,
        )
