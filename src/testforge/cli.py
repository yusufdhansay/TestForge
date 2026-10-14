import argparse
import math
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import urlsplit

from testforge.executor import HTTPTestExecutor
from testforge.generator import ContractTestGenerator
from testforge.html_reporter import HTMLReportExporter
from testforge.json_reporter import JSONReportExporter
from testforge.parser import OpenAPIParser
from testforge.reporter import ExecutionReporter


def get_version() -> str:
    """Return the installed TestForge package version."""
    try:
        return version("testforge")
    except PackageNotFoundError:
        return "unknown"


def positive_milliseconds(value: str) -> float:
    """Parse a finite, strictly positive response-time threshold."""
    try:
        threshold = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "Response-time threshold must be a positive number of milliseconds."
        ) from error

    if not math.isfinite(threshold) or threshold <= 0:
        raise argparse.ArgumentTypeError(
            "Response-time threshold must be a finite positive number of milliseconds."
        )
    return threshold


def build_parser() -> argparse.ArgumentParser:
    """Create the TestForge command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="testforge",
        description="Automated API contract testing and reliability platform.",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"TestForge {get_version()}",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        title="commands",
    )

    run_parser = subparsers.add_parser(
        "run",
        help="Generate and execute API contract tests.",
        description="Run API contract tests from an OpenAPI specification.",
    )

    run_parser.add_argument(
        "spec",
        help="Path to an OpenAPI JSON or YAML specification.",
    )

    run_parser.add_argument(
        "--base-url",
        required=True,
        help="Base URL of the API under test.",
    )

    run_parser.add_argument(
        "--report",
        choices=["json", "html"],
        default="json",
        help="Report format (default: json).",
    )

    run_parser.add_argument(
        "--output",
        help="Output file path for the execution report.",
    )

    run_parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Explicitly allow real HTTP requests.",
    )

    run_parser.add_argument(
        "--allow-state-changes",
        action="store_true",
        help="Allow POST, PUT, PATCH, and DELETE requests.",
    )

    run_parser.add_argument(
        "--max-response-time",
        type=positive_milliseconds,
        default=None,
        metavar="MS",
        help="Maximum allowed response time in milliseconds (positive number).",
    )

    return parser


def validate_report_destination(
    output_path: Path,
    report_format: str,
) -> None:
    """Validate report destination before executing API requests."""
    expected_suffix = f".{report_format}"

    if output_path.suffix.lower() != expected_suffix:
        raise ValueError(f"Report output must be a {report_format.upper()} file")

    if not output_path.parent.is_dir():
        raise FileNotFoundError(
            f"Output directory does not exist: {output_path.parent}"
        )

    if output_path.exists():
        raise FileExistsError(f"Report already exists: {output_path}")


def run_tests(args: argparse.Namespace) -> int:
    """Generate, execute, and report API contract tests."""
    if not args.allow_network:
        print(
            "Error: Network access is disabled. "
            "Pass --allow-network to execute real HTTP requests.",
            file=sys.stderr,
        )
        return 2

    parsed_url = urlsplit(args.base_url)

    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.hostname
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.query
        or parsed_url.fragment
    ):
        print("Error: Invalid base URL.", file=sys.stderr)
        return 2

    approved_origin = f"{parsed_url.scheme}://{parsed_url.netloc}"

    try:
        output_path = Path(args.output or f"testforge-report.{args.report}")
        validate_report_destination(output_path, args.report)

        specification = OpenAPIParser(args.spec).parse()
        test_cases = ContractTestGenerator(specification).generate()

        if not test_cases:
            print("Error: No contract tests were generated.", file=sys.stderr)
            return 2

        if args.max_response_time is not None:
            for test_case in test_cases:
                test_case.max_response_time_ms = args.max_response_time

        with HTTPTestExecutor(
            base_url=args.base_url,
            allow_network=True,
            approved_origins={approved_origin},
            allow_state_changes=args.allow_state_changes,
        ) as executor:
            results = [executor.execute(test_case) for test_case in test_cases]

        summary = ExecutionReporter().summarize(results)

        print(f"Total:      {summary.total}")
        print(f"Passed:     {summary.passed}")
        print(f"Failed:     {summary.failed}")
        print(f"Unasserted: {summary.unasserted}")
        print(f"Errors:     {summary.errors}")
        print(f"Pass rate:  {summary.pass_rate:.2f}%")

        if args.report == "json":
            JSONReportExporter().export(results, output_path)
        else:
            HTMLReportExporter().export(results, output_path)

        print(f"Report:     {output_path}")

        if summary.failed > 0 or summary.errors > 0:
            return 1
        return 0

    except (OSError, ValueError, KeyError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    """Run the TestForge command-line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return run_tests(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
