from html import escape
from pathlib import Path

from testforge.coverage import CoverageReport
from testforge.execution_models import ExecutionResult
from testforge.reporter import ExecutionReporter


class HTMLReportExporter:
    def __init__(self):
        self.reporter = ExecutionReporter()

    def build_report(
        self,
        results: list[ExecutionResult],
        coverage: CoverageReport | None = None,
    ) -> str:
        summary = self.reporter.summarize(results)

        def format_time(value: float | None) -> str:
            return "N/A" if value is None else f"{value:.2f} ms"

        rows = []

        for result in results:
            status = result.status.value

            rows.append(
                "<tr>"
                f"<td>{escape(result.test_id)}</td>"
                f'<td class="status-{status}">{status.upper()}</td>'
                f"<td>{result.actual_status_code if result.actual_status_code is not None else 'N/A'}</td>"
                f"<td>{format_time(result.response_time_ms)}</td>"
                f"<td>{escape(result.error_message or '')}</td>"
                "</tr>"
            )

        rows_html = "\n".join(rows)

        coverage_html = ""

        if coverage is not None:
            method_rows = []

            for method in coverage.methods:
                method_rows.append(
                    "<tr>"
                    f"<td>{escape(method.method)}</td>"
                    f"<td>{method.total_operations}</td>"
                    f"<td>{method.generated_operations}</td>"
                    f"<td>{method.executed_operations}</td>"
                    f"<td>{method.generated_coverage_percent:.2f}%</td>"
                    f"<td>{method.executed_coverage_percent:.2f}%</td>"
                    "</tr>"
                )

            method_rows_html = "\n".join(method_rows)

            if not method_rows_html:
                method_rows_html = (
                    '<tr><td colspan="6">No API operations found.</td></tr>'
                )

            if coverage.untested_operations:
                untested_html = "\n".join(
                    f"<li><code>{escape(operation)}</code></li>"
                    for operation in coverage.untested_operations
                )
                untested_html = f"<ul>{untested_html}</ul>"
            else:
                untested_html = (
                    "<p>All documented API operations were executed.</p>"
                    if coverage.total_operations
                    else "<p>No documented API operations.</p>"
                )

            coverage_html = f"""
    <section class="panel">
        <h2>Contract Coverage</h2>
        <div class="metrics">
            <div>
                <div class="metric-label">Total Operations</div>
                <div class="metric-value">{coverage.total_operations}</div>
            </div>
            <div>
                <div class="metric-label">Generated Operations</div>
                <div class="metric-value">{coverage.generated_operations}</div>
            </div>
            <div>
                <div class="metric-label">Executed Operations</div>
                <div class="metric-value">{coverage.executed_operations}</div>
            </div>
            <div>
                <div class="metric-label">Generated Coverage</div>
                <div class="metric-value">{coverage.generated_coverage_percent:.2f}%</div>
            </div>
            <div>
                <div class="metric-label">Executed Coverage</div>
                <div class="metric-value">{coverage.executed_coverage_percent:.2f}%</div>
            </div>
            <div>
                <div class="metric-label">Untested Operations</div>
                <div class="metric-value">{len(coverage.untested_operations)}</div>
            </div>
        </div>
    </section>

    <section class="panel">
        <h2>Coverage by HTTP Method</h2>
        <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th>Method</th>
                        <th>Total</th>
                        <th>Generated</th>
                        <th>Executed</th>
                        <th>Generated Coverage</th>
                        <th>Executed Coverage</th>
                    </tr>
                </thead>
                <tbody>
                    {method_rows_html}
                </tbody>
            </table>
        </div>
    </section>

    <section class="panel">
        <h2>Untested API Operations</h2>
        {untested_html}
    </section>
"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TestForge Execution Report</title>
<style>
:root {{
    color-scheme: light;
}}
* {{
    box-sizing: border-box;
}}
body {{
    margin: 0;
    padding: 40px 24px;
    background: #f3f6fb;
    color: #182235;
    font-family: Arial, Helvetica, sans-serif;
}}
.container {{
    max-width: 1100px;
    margin: auto;
}}
h1 {{
    margin-bottom: 8px;
}}
.subtitle {{
    color: #64748b;
    margin-bottom: 32px;
}}
.cards {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
}}
.card {{
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 20px;
}}
.card .label {{
    color: #64748b;
    font-size: 13px;
}}
.card .value {{
    margin-top: 10px;
    font-size: 28px;
    font-weight: bold;
}}
.panel {{
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 24px;
}}
.metrics {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 20px;
}}
.metric-label {{
    font-size: 13px;
    color: #64748b;
}}
.metric-value {{
    margin-top: 8px;
    font-size: 18px;
    font-weight: bold;
}}
.table-wrapper {{
    overflow-x: auto;
}}
table {{
    width: 100%;
    border-collapse: collapse;
}}
th, td {{
    padding: 14px;
    border-bottom: 1px solid #e2e8f0;
    text-align: left;
    font-size: 14px;
}}
th {{
    color: #64748b;
    font-size: 12px;
    text-transform: uppercase;
}}
.status-passed {{
    color: #15803d;
    font-weight: bold;
}}
.status-failed, .status-error {{
    color: #b91c1c;
    font-weight: bold;
}}
.status-unasserted {{
    color: #a16207;
    font-weight: bold;
}}
code {{
    background: #f1f5f9;
    border-radius: 4px;
    padding: 2px 6px;
    overflow-wrap: anywhere;
}}
li {{
    margin-bottom: 10px;
}}
</style>
</head>
<body>
<main class="container">
    <h1>TestForge Execution Report</h1>
    <p class="subtitle">API Contract Testing Results</p>

    <section class="cards">
        <div class="card"><div class="label">Total Tests</div><div class="value">{summary.total}</div></div>
        <div class="card"><div class="label">Passed</div><div class="value">{summary.passed}</div></div>
        <div class="card"><div class="label">Failed</div><div class="value">{summary.failed}</div></div>
        <div class="card"><div class="label">Unasserted</div><div class="value">{summary.unasserted}</div></div>
        <div class="card"><div class="label">Errors</div><div class="value">{summary.errors}</div></div>
        <div class="card"><div class="label">Pass Rate</div><div class="value">{summary.pass_rate:.2f}%</div></div>
    </section>

    <section class="panel">
        <h2>Response Time Statistics</h2>
        <div class="metrics">
            <div><div class="metric-label">Average</div><div class="metric-value">{format_time(summary.average_response_time_ms)}</div></div>
            <div><div class="metric-label">Minimum</div><div class="metric-value">{format_time(summary.min_response_time_ms)}</div></div>
            <div><div class="metric-label">Maximum</div><div class="metric-value">{format_time(summary.max_response_time_ms)}</div></div>
            <div><div class="metric-label">P95</div><div class="metric-value">{format_time(summary.p95_response_time_ms)}</div></div>
        </div>
    </section>

    {coverage_html}

    <section class="panel">
        <h2>Individual Test Results</h2>
        <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th>Test ID</th>
                        <th>Status</th>
                        <th>HTTP Code</th>
                        <th>Response Time</th>
                        <th>Error</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
    </section>
</main>
</body>
</html>
"""

    def export(
        self,
        results: list[ExecutionResult],
        output_path: str | Path,
        coverage: CoverageReport | None = None,
    ) -> Path:
        path = Path(output_path)

        if path.suffix.lower() != ".html":
            raise ValueError("Report output must be an HTML file")

        if not path.parent.is_dir():
            raise FileNotFoundError(f"Output directory does not exist: {path.parent}")

        html = self.build_report(
            results,
            coverage=coverage,
        )

        with path.open("x", encoding="utf-8") as file:
            file.write(html)

        return path
