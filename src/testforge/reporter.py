from collections import Counter
from math import ceil
from statistics import mean

from testforge.execution_models import ExecutionResult, ExecutionStatus
from testforge.report_models import ExecutionSummary


class ExecutionReporter:
    def summarize(
        self,
        results: list[ExecutionResult],
    ) -> ExecutionSummary:
        counts = Counter(result.status for result in results)

        total = len(results)
        passed = counts[ExecutionStatus.PASSED]
        failed = counts[ExecutionStatus.FAILED]
        unasserted = counts[ExecutionStatus.UNASSERTED]
        errors = counts[ExecutionStatus.ERROR]

        pass_rate = round(passed / total * 100, 2) if total else 0.0

        response_times = sorted(
            result.response_time_ms
            for result in results
            if result.response_time_ms is not None
        )

        if response_times:
            average_time = round(mean(response_times), 2)
            min_time = response_times[0]
            max_time = response_times[-1]

            # Nearest-rank P95 percentile.
            p95_index = ceil(0.95 * len(response_times)) - 1
            p95_time = response_times[p95_index]
        else:
            average_time = None
            min_time = None
            max_time = None
            p95_time = None

        return ExecutionSummary(
            total=total,
            passed=passed,
            failed=failed,
            unasserted=unasserted,
            errors=errors,
            pass_rate=pass_rate,
            average_response_time_ms=average_time,
            min_response_time_ms=min_time,
            max_response_time_ms=max_time,
            p95_response_time_ms=p95_time,
        )
