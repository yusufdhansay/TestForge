import json
from pathlib import Path

from testforge.execution_models import ExecutionResult
from testforge.reporter import ExecutionReporter


class JSONReportExporter:
    def __init__(self):
        self.reporter = ExecutionReporter()

    def build_report(
        self,
        results: list[ExecutionResult],
    ) -> dict:
        summary = self.reporter.summarize(results)

        return {
            "summary": summary.model_dump(mode="json"),
            "results": [result.model_dump(mode="json") for result in results],
        }

    def export(
        self,
        results: list[ExecutionResult],
        output_path: str | Path,
    ) -> Path:
        path = Path(output_path)

        if path.suffix.lower() != ".json":
            raise ValueError("Report output must be a JSON file")

        report = self.build_report(results)

        # Do not create directories implicitly.
        # The destination directory must already exist.
        if not path.parent.is_dir():
            raise FileNotFoundError(f"Output directory does not exist: {path.parent}")

        # Avoid overwriting existing reports.
        with path.open("x", encoding="utf-8") as file:
            json.dump(report, file, indent=2, allow_nan=False)
            file.write("\n")

        return path
