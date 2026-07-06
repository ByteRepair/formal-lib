# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

formal-lib is a Python library that parses unstructured output from software verifiers (ESBMC, CBMC, Clang, PyTest) into structured JSON with issues, stack traces, and counterexamples. It provides both a CLI (`pf`) and a programmatic API (`VerifierRunner`).

## Commands

```bash
# Install dependencies (uses hatch)
hatch env create

# Run unit tests (excludes regression tests by default)
hatch test

# Run a single test
hatch test tests/test_specs/test_pytest_spec.py::test_function_name

# Run regression tests (data-driven .log/.json pairs)
hatch run regression:test

# Type checking
hatch run types:check

# Build
hatch build
```

## Architecture

The library uses a **specification-driven regex parsing** pattern with three layers:

1. **Specs** (`formal_lib/specs/`) — Each verifier backend defines an `IssueRegexSpec` containing regex patterns for extracting issue blocks, error types, messages, severity, and nested `StackTraceRegexSpec`/`CounterexampleRegexSpec` for traces. Specs also define a `success` pattern to determine verification outcome from the output text (with `negate_success` for backends where absence of failure indicates success). Specs are plain dataclass instances (e.g., `esbmc_spec`, `cbmc_spec`, `clang_spec`, `pytest_spec`). Any `block` pattern can be wrapped with `missing_hint("Needs --flag")(pattern)` to annotate it — when the block fails to match and verification failed, the hint is collected into `VerifierOutput.hints` and displayed by the CLI.

2. **Parser** (`formal_lib/issue_parser.py`) — `IssueSpecOutputParser` applies a spec's regex hierarchy to raw output: the `success` pattern determines the `successful` flag, the block pattern finds issue boundaries, then field patterns extract structured data from each block. Traces are parsed via a nested block→entry→fields hierarchy.

3. **Runner** (`formal_lib/verifier_runner.py`) — `VerifierRunner` executes a verifier command, feeds output to the parser, and optionally caches results using content-based hashing (zlib.adler32 + pickle).

**Data models** (all Pydantic `BaseModel`):
- `Issue` / `VerifierIssue` (`issue.py`) — error type, message, severity, stack trace; `VerifierIssue` adds counterexample traces
- `ProgramTrace` / `CounterexampleProgramTrace` (`program_trace.py`) — file path, line number, function name; counterexample variant adds variable assignments
- `VerifierOutput` (`verifier_output.py`) — result container with `successful` bool, issues list, convenience properties for primary issue access

**CLI** (`__main__.py`) — reads from stdin or runs a command after `--`, selects spec via `--backend` (auto-detected when omitted), outputs in `pretty`/`json`/`json-compact` format.

## Testing

- **Unit tests** in `tests/test_specs/` — test individual spec parsers against sample data in `tests/test_specs/data/`
- **Regression tests** in `tests/regressions/` — data-driven: drop a `.log` and matching `.json` into `tests/regressions/samples/<spec>/` and the test auto-discovers them. The `.json` is the expected CLI JSON output minus the `output` field. Marked with `@pytest.mark.regression`, excluded from default pytest runs.

## Adding a New Verifier Backend

Create a new `IssueRegexSpec` instance in `formal_lib/specs/`, including a `success` pattern for determining verification outcome. Wrap any `block` pattern with `missing_hint("Needs --flag")(pattern)` when the verifier requires a specific flag for that data. Export it from `formal_lib/specs/__init__.py`, add it to the `SPECS` dict, and add a CLI flag in `__main__.py`.
