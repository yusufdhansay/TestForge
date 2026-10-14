# TestForge
[![TestForge CI](https://github.com/yusufdhansay/TestForge/actions/workflows/ci.yml/badge.svg)](https://github.com/yusufdhansay/TestForge/actions/workflows/ci.yml)

An automated API testing and reliability engineering platform.

## Vision

TestForge helps developers discover API endpoints,
generate contract tests, execute them, and analyze failures.

## Current Scope

Phase 0: Project initialization.

## Planned Features

- OpenAPI specification parsing
- Automated API contract test generation
- HTTP test execution
- Structured test reporting
- CI/CD integration
- Performance and security testing

## Development

Requires Python 3.11+.

Install:

    python -m pip install -e ".[dev]"

Run tests:

    python -m pytest -v

Run linting:

    python -m ruff check .