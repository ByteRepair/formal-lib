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
hatch test -- tests/regressions/ -m regression -o "addopts="

# Type checking
hatch run types:check

# Check that no two specs of one backend support the same verifier version
# (-v also lists every spec and the versions it supports)
hatch run check-specs

# Build
hatch build
```

Hatch scripts only forward extra CLI arguments when their definition in `pyproject.toml` contains an explicit `{args}` placeholder (e.g. `check-specs = "python -m formal_lib.specs.conflicts {args}"`) — without it, hatch silently swallows flags like `-v`.

## Architecture

The library uses a **specification-driven regex parsing** pattern with three layers:

1. **Specs** (`formal_lib/specs/`) — Each verifier backend defines an `IssueRegexSpec` containing regex patterns for extracting issue blocks, error types, messages, severity, and nested `StackTraceRegexSpec`/`CounterexampleRegexSpec` for traces. The verification outcome is a data-driven baseline — a run passes when it has no error-severity issue — that a spec can gate with an optional positive `success` pattern (fail-closed: it must match to pass, e.g. ESBMC/CBMC's `VERIFICATION SUCCESSFUL`) and/or a `failure` pattern (a match forces failure — the gate for backends whose failures don't surface as issues by default, e.g. Kani without `--trace`). Specs are plain dataclass instances (e.g., `esbmc_spec`, `cbmc_spec`, `clang_spec`, `pytest_spec`). Each spec declares the verifier `versions` it supports — a list of exact `Version` and/or inclusive `VersionRange` entries (`formal_lib/version.py`; a `None` bound means unbounded, default is a single all-versions range). Any `block` pattern can be wrapped with `missing_hint("Needs --flag")(pattern)` to annotate it — when the block fails to match and verification failed, the hint is collected into `VerifierOutput.hints` and displayed by the CLI.

2. **Parser** (`formal_lib/issue_parser.py`) — `IssueSpecOutputParser` applies a spec's regex hierarchy to raw output: the block pattern finds issue boundaries and field patterns extract structured data from each block, then `_is_successful` computes the `successful` flag from the parsed issues' severities gated by the spec's `success`/`failure` patterns. Traces are parsed via a nested block→entry→fields hierarchy.

3. **Runner** (`formal_lib/verifier_runner.py`) — `VerifierRunner` executes a verifier command, feeds output to the parser, and optionally caches results using content-based hashing (zlib.adler32 + pickle).

**Data models** (all Pydantic `BaseModel`):
- `Issue` / `VerifierIssue` (`issue.py`) — error type, message, severity, stack trace; `VerifierIssue` adds counterexample traces
- `ProgramTrace` / `CounterexampleProgramTrace` (`program_trace.py`) — file path, line number, function name; counterexample variant adds variable assignments
- `VerifierOutput` (`verifier_output.py`) — result container with `successful` bool, issues list, convenience properties for primary issue access

**CLI** (`__main__.py`) — reads from stdin or runs a command after `--`, selects spec via `--backend` (auto-detected when omitted), outputs in `pretty`/`json`/`json-compact` format.

## Testing

- **Unit tests** in `tests/test_specs/` — cover only behaviour a regression fixture can't express: auto-detection, missing-flag hints (excluded from serialized output), derived-property logic (`function_name`/`error_location` precedence), and verdict combinations driven by synthetic specs. Anything that's "parse a real log with a registered backend and check the structured output" belongs in the regression suite, not here.
- **Regression tests** in `tests/regressions/` — data-driven: drop a `.log` and matching `.json` into `tests/regressions/samples/<backend>/` and the test auto-discovers them. The `.json` is the expected CLI JSON output minus the `output` field. Marked with `@pytest.mark.regression`, excluded from default pytest runs.
  - A directory component named as a version range (`v6.7.0-v6.10.0`, `v6.7.0-`, `-v6.10.0`, or exact `v6.7.1` — see `VERSION_RANGE_PATTERN`) constrains the samples beneath it: they run only against the backend's specs whose `versions` overlap that range. Samples outside a version directory run against every spec of their backend. Name version directories after the tool version the `.log` itself proves (its version banner) — don't invent ranges the log doesn't evidence.
  - The `.log` must be **genuine verifier output** (captured from a real run), and the `.json` must be the **exact** structured output the parser produces from that log — generate it by running `pf` (`python -m formal_lib --backend <spec> --format json-compact`) against the log and stripping the `output` field, then read it to confirm it faithfully reflects the log. Never hand-write or hallucinate field values (messages, line numbers, trace entries, severities): every value in the `.json` must be traceable to something actually present in the `.log`. If the generated output looks wrong, the fix is in the spec/parser, not in editing the `.json` to what you wish it said.

## Adding a New Verifier Backend

Create a new `IssueRegexSpec` instance in `formal_lib/specs/`. The verdict defaults to "no error-severity issue"; add a `success` pattern (positive verdict line) and/or a `failure` pattern (forces failure) only if the backend needs one. Wrap any `block` pattern with `missing_hint("Needs --flag")(pattern)` when the verifier requires a specific flag for that data. Export it from `formal_lib/specs/__init__.py` and add it to the `SPECS` dict, which maps each backend name (the `--backend` choice in `__main__.py`) to a list of versioned specs.

When a verifier changes its output format in a new version, add a second spec to the same backend's list (newest first) and constrain both specs' `versions` so their ranges don't overlap — `hatch run check-specs` fails on any same-backend overlap (a spec conflict). `resolve_spec` picks within a backend by trying each spec's `detect` pattern, falling back to the first listed.
