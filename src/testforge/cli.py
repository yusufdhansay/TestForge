import argparse
import math
import os
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import urlsplit

from testforge.coverage import ContractCoverageAnalyzer
from testforge.executor import (
    HTTPTestExecutor,
    validate_api_key_configuration,
    validate_basic_auth,
    validate_bearer_token,
)
from testforge.generator import ContractTestGenerator
from testforge.html_reporter import HTMLReportExporter
from testforge.json_reporter import JSONReportExporter
from testforge.parser import OpenAPIParser
from testforge.reporter import ExecutionReporter
from testforge.security import analyze_security
from testforge.security_routing import build_operation_auth

HTTP_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
    "trace",
}


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


def coverage_percentage(value: str) -> float:
    """Parse a finite coverage percentage between 0 and 100."""
    try:
        percentage = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "Coverage threshold must be a number between 0 and 100."
        ) from error

    if not math.isfinite(percentage) or not 0 <= percentage <= 100:
        raise argparse.ArgumentTypeError(
            "Coverage threshold must be a finite number between 0 and 100."
        )

    return percentage


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
        "--bearer-token",
        default=None,
        metavar="TOKEN",
        help=(
            "Bearer token for API authentication. "
            "Prefer TESTFORGE_BEARER_TOKEN to avoid shell history exposure."
        ),
    )

    run_parser.add_argument(
        "--api-key",
        default=None,
        metavar="KEY",
        help=("API key credential. Prefer the TESTFORGE_API_KEY environment variable."),
    )

    run_parser.add_argument(
        "--api-key-name",
        default=None,
        metavar="NAME",
        help=(
            "Header or query parameter name for the API key. "
            "Defaults to X-API-Key for headers or api_key for queries."
        ),
    )

    run_parser.add_argument(
        "--api-key-in",
        choices=["header", "query"],
        default="header",
        help="Send the API key in a header or query parameter (default: header).",
    )

    run_parser.add_argument(
        "--basic-username",
        default=None,
        metavar="USERNAME",
        help="HTTP Basic authentication username. Prefer TESTFORGE_BASIC_USERNAME.",
    )

    run_parser.add_argument(
        "--basic-password",
        default=None,
        metavar="PASSWORD",
        help=(
            "HTTP Basic authentication password. "
            "Prefer TESTFORGE_BASIC_PASSWORD to avoid shell history exposure."
        ),
    )

    run_parser.add_argument(
        "--max-response-time",
        type=positive_milliseconds,
        default=None,
        metavar="MS",
        help="Maximum allowed response time in milliseconds (positive number).",
    )

    run_parser.add_argument(
        "--min-generated-coverage",
        type=coverage_percentage,
        default=None,
        metavar="PERCENT",
        help="Minimum required generated operation coverage (0-100).",
    )

    run_parser.add_argument(
        "--min-executed-coverage",
        type=coverage_percentage,
        default=None,
        metavar="PERCENT",
        help="Minimum required executed operation coverage (0-100).",
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


def has_explicit_security(document: dict) -> bool:
    """Detect explicit OpenAPI security declarations.

    Security scheme definitions alone do not activate authentication
    routing. Both security: [] and nonempty security requirements
    count as explicit declarations.
    """
    if "security" in document:
        return True

    paths = document.get("paths", {})

    if not isinstance(paths, dict):
        return False

    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue

        for method, operation in path_item.items():
            if (
                method.lower() in HTTP_METHODS
                and isinstance(operation, dict)
                and "security" in operation
            ):
                return True

    return False


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
        bearer_token = args.bearer_token

        if bearer_token is None:
            bearer_token = os.environ.get("TESTFORGE_BEARER_TOKEN")

        if bearer_token is not None:
            bearer_token = validate_bearer_token(bearer_token)

        api_key = args.api_key

        if api_key is None:
            api_key = os.environ.get("TESTFORGE_API_KEY")

        basic_username = args.basic_username
        basic_password = args.basic_password

        if basic_username is None:
            basic_username = os.environ.get("TESTFORGE_BASIC_USERNAME")

        if basic_password is None:
            basic_password = os.environ.get("TESTFORGE_BASIC_PASSWORD")

        basic_username, basic_password = validate_basic_auth(
            basic_username,
            basic_password,
        )

        if bearer_token is not None and basic_username is not None:
            raise ValueError("Basic and Bearer authentication cannot be used together")

        (
            api_key,
            api_key_name,
            api_key_location,
        ) = validate_api_key_configuration(
            api_key=api_key,
            api_key_name=args.api_key_name,
            api_key_location=args.api_key_in,
            bearer_token=bearer_token,
        )

        if (
            basic_username is not None
            and api_key is not None
            and api_key_location == "header"
            and api_key_name.lower() == "authorization"
        ):
            raise ValueError(
                "Basic authentication and an Authorization API key conflict"
            )

        output_path = Path(args.output or f"testforge-report.{args.report}")
        validate_report_destination(output_path, args.report)

        parser = OpenAPIParser(args.spec)
        document = parser.load()

        security_analysis = analyze_security(document)

        operation_auth = build_operation_auth(
            security_analysis,
            bearer_token=bearer_token,
            basic_username=basic_username,
            api_key=api_key,
            api_key_name=api_key_name,
            api_key_location=api_key_location,
        )

        specification = parser.parse()
        test_cases = ContractTestGenerator(specification).generate()

        if not test_cases:
            print(
                "Error: No contract tests were generated.",
                file=sys.stderr,
            )
            return 2

        if args.max_response_time is not None:
            for test_case in test_cases:
                test_case.max_response_time_ms = args.max_response_time

        # Only pass optional credentials when configured.
        # Existing mocked constructors remain compatible.
        executor_options = {
            "base_url": args.base_url,
            "allow_network": True,
            "approved_origins": {approved_origin},
            "allow_state_changes": args.allow_state_changes,
        }

        # Preserve legacy authentication when no security requirements
        # are explicitly declared. Defining securitySchemes alone
        # does not change the existing credential behavior.
        if has_explicit_security(document):
            executor_options["operation_auth"] = operation_auth

        if bearer_token is not None:
            executor_options["bearer_token"] = bearer_token

        if api_key is not None:
            executor_options["api_key"] = api_key
            executor_options["api_key_name"] = api_key_name
            executor_options["api_key_location"] = api_key_location

        if basic_username is not None:
            executor_options["basic_username"] = basic_username
            executor_options["basic_password"] = basic_password

        with HTTPTestExecutor(**executor_options) as executor:
            results = [executor.execute(test_case) for test_case in test_cases]

        summary = ExecutionReporter().summarize(results)

        coverage = ContractCoverageAnalyzer().analyze(
            specification,
            test_cases,
            results,
        )

        print(f"Total:      {summary.total}")
        print(f"Passed:     {summary.passed}")
        print(f"Failed:     {summary.failed}")
        print(f"Unasserted: {summary.unasserted}")
        print(f"Errors:     {summary.errors}")
        print(f"Pass rate:  {summary.pass_rate:.2f}%")

        print()
        print("Contract Coverage")
        print("-----------------------------")
        print(f"Total operations:       {coverage.total_operations}")
        print(f"Generated coverage:     {coverage.generated_coverage_percent:.2f}%")
        print(f"Executed coverage:      {coverage.executed_coverage_percent:.2f}%")
        print(f"Untested operations:    {len(coverage.untested_operations)}")

        if coverage.untested_operations:
            print()
            print("Untested API operations:")

            for operation in coverage.untested_operations:
                print(f"  - {operation}")

        gate_failures = []

        if (
            args.min_generated_coverage is not None
            and coverage.generated_coverage_percent < args.min_generated_coverage
        ):
            gate_failures.append(
                "Generated coverage "
                f"{coverage.generated_coverage_percent:.2f}% "
                "is below the required "
                f"{args.min_generated_coverage:.2f}%."
            )

        if (
            args.min_executed_coverage is not None
            and coverage.executed_coverage_percent < args.min_executed_coverage
        ):
            gate_failures.append(
                "Executed coverage "
                f"{coverage.executed_coverage_percent:.2f}% "
                "is below the required "
                f"{args.min_executed_coverage:.2f}%."
            )

        if args.report == "json":
            JSONReportExporter().export(
                results,
                output_path,
                coverage=coverage,
            )
        else:
            HTMLReportExporter().export(
                results,
                output_path,
                coverage=coverage,
            )

        print()
        print(f"Report:     {output_path}")

        if gate_failures:
            print()
            print(
                "CI Quality Gates: FAILED",
                file=sys.stderr,
            )

            for failure in gate_failures:
                print(
                    f"  - {failure}",
                    file=sys.stderr,
                )

        elif (
            args.min_generated_coverage is not None
            or args.min_executed_coverage is not None
        ):
            print("CI Quality Gates: PASSED")

        if summary.failed > 0 or summary.errors > 0 or gate_failures:
            return 1

        return 0

    except (OSError, ValueError, KeyError, TypeError) as error:
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
