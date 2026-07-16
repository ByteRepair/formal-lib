# Author: Yiannis Charalambous

"""Tests for the verdict logic in IssueSpecOutputParser._is_successful.

The verdict is a data-driven baseline (no error-severity issue) gated by the spec's
optional `success` (positive, fail-closed) and `failure` (gate) patterns. These use a
tiny synthetic spec: a line `ISSUE <severity>` becomes one issue of that severity, and
`PASS` / `FAIL` markers drive the patterns.
"""

from formal_lib import IssueSpecOutputParser
from formal_lib.specs.base import IssueRegexSpec, StackTraceRegexSpec

# A stack-trace spec whose block never matches, so issues have an empty stack trace.
_NO_TRACE = StackTraceRegexSpec(
    block=r"ZZZ_NOMATCH", trace_entry=r"ZZZ", trace_index=r"ZZZ",
    path=r"ZZZ", name=r"ZZZ", line_index=r"ZZZ",
)


def _verdict(output: str, *, success: str | None = None, failure: str | None = None) -> bool:
    spec = IssueRegexSpec(
        block=r"^ISSUE \w+$",
        error_type=r"^(ISSUE)",
        message=r"^ISSUE (\w+)",
        severity=r"^ISSUE (\w+)",
        stack_trace_spec=_NO_TRACE,
        success=success,
        failure=failure,
    )
    return IssueSpecOutputParser(spec).parse_output(output).successful


# --- data-driven baseline (no patterns) ---

def test_no_patterns_error_issue_fails() -> None:
    assert _verdict("ISSUE error") is False


def test_no_patterns_warning_issue_passes() -> None:
    """A warning-severity issue must not flip the verdict."""
    assert _verdict("ISSUE warning") is True


def test_no_patterns_no_issue_passes() -> None:
    assert _verdict("nothing to see") is True


# --- success pattern: positive confirmation, fail-closed ---

def test_success_pattern_must_match_to_pass() -> None:
    assert _verdict("PASS", success=r"PASS") is True
    # No match -> failed, even with no issues (fail-closed on garbage/crash output).
    assert _verdict("truncated output", success=r"PASS") is False


def test_success_pattern_overridden_by_error_issue() -> None:
    """Even if the success line matched, an error issue means not successful."""
    assert _verdict("PASS\nISSUE error", success=r"PASS") is False


# --- failure pattern: the gate for no-issue failures ---

def test_failure_pattern_gates_a_failure_with_no_issues() -> None:
    """The key case the data-driven baseline can't see: a failure that produced no
    issues (e.g. Kani without --trace) is still caught by the failure pattern."""
    assert _verdict("FAIL", failure=r"FAIL") is False
    assert _verdict("all clear", failure=r"FAIL") is True


def test_error_issue_catches_a_missed_failure_pattern() -> None:
    """The independent gates close the fail-open: if the failure pattern misses but
    the failure surfaced as an error issue, the run is still reported as failed."""
    assert _verdict("ISSUE error", failure=r"FAIL") is False


# --- both patterns ---

def test_both_patterns_failure_wins() -> None:
    assert _verdict("PASS", success=r"PASS", failure=r"FAIL") is True
    assert _verdict("PASS\nFAIL", success=r"PASS", failure=r"FAIL") is False
