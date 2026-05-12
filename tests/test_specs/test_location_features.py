# Author: Yiannis Charalambous

"""Tests for the deepest_first trace-order wrapper and the error_location
override on Issue. Both target the failure mode where Issue.file_path
returned the wrong end of an ESBMC stack trace under contract
instrumentation."""

from pathlib import Path

import pytest

from formal_lib import IssueSpecOutputParser
from formal_lib.issue import ErrorLocation, Issue, VerifierIssue
from formal_lib.program_trace import ProgramTrace
from formal_lib.specs.base import (
    CounterexampleRegexSpec,
    ErrorLocationRegexSpec,
    IssueRegexSpec,
    StackTraceRegexSpec,
    deepest_first,
)
from formal_lib.specs.esbmc import esbmc_spec


# A pared-down esbmc-shaped log with TWO stack frames at different lines.
# The verifier prints frame 99 (deepest) first and frame 11 (outermost)
# last — the deepest_first wrapper should make stack_trace[-1] = the
# deepest frame regardless of source order.
_TWO_FRAME_LOG = """ESBMC version 8.2.0 64-bit x86_64 linux
[Counterexample]


State 1 file demo.c line 99 column 3 function inner thread 0
----------------------------------------------------
Violated property:
  file demo.c line 99 column 3 function inner
Stack trace:
  c:@F@inner at file demo.c line 99 column 3
  c:@F@outer at file demo.c line 11 column 5
  assertion failed
"""


def _spec_with_trace_order(*, deepest_first_wrapped: bool) -> IssueRegexSpec:
    """Build a minimal esbmc-flavoured spec; toggle deepest_first wrapping."""
    trace_pat = r"^[^\n]*\bfile\s+\S+\s+line\s+\d+[^\n]*"
    return IssueRegexSpec(
        block=r"\[Counterexample\].*?(?=\[Counterexample\]|\Z)",
        error_type=r"Stack trace:\n(?:\s+c:@\S*[^\n]*\n)*\s+(\S+)",
        message=r"Stack trace:\n(?:\s+c:@\S*[^\n]*\n)*\s+\S+\s+(.+?)$",
        severity=r"(Violated property)",
        stack_trace_spec=StackTraceRegexSpec(
            block=r"Stack trace:\n(?:\s+[^\n]+\n)*",
            trace_entry=(
                deepest_first()(trace_pat)
                if deepest_first_wrapped
                else trace_pat
            ),
            trace_index=r"^",
            path=r"file\s+(\S+)",
            name=r"c:@\w@(\S+)",
            line_index=r"line\s+(\d+)",
        ),
    )


def test_deepest_first_reverses_trace_list() -> None:
    """With the wrapper, stack_trace[-1] is the deepest frame (line 99)."""
    parser = IssueSpecOutputParser(_spec_with_trace_order(deepest_first_wrapped=True))
    result = parser.parse_output(_TWO_FRAME_LOG)

    assert len(result.issues) == 1
    issue = result.issues[0]
    assert len(issue.stack_trace) == 2
    assert issue.stack_trace[0].line_idx == 10  # outermost frame, line 11 → 0-based 10
    assert issue.stack_trace[-1].line_idx == 98  # deepest frame, line 99 → 0-based 98


def test_without_deepest_first_preserves_source_order() -> None:
    """Without the wrapper, stack_trace[-1] is the outermost frame (line 11)."""
    parser = IssueSpecOutputParser(_spec_with_trace_order(deepest_first_wrapped=False))
    result = parser.parse_output(_TWO_FRAME_LOG)

    assert len(result.issues) == 1
    issue = result.issues[0]
    assert len(issue.stack_trace) == 2
    # In source order: deepest first, outermost last.
    assert issue.stack_trace[0].line_idx == 98
    assert issue.stack_trace[-1].line_idx == 10


def test_deepest_first_reindexes_after_reverse() -> None:
    """trace_index reflects post-reversal position, not source-order position."""
    parser = IssueSpecOutputParser(_spec_with_trace_order(deepest_first_wrapped=True))
    issue = parser.parse_output(_TWO_FRAME_LOG).issues[0]

    assert [t.trace_index for t in issue.stack_trace] == [0, 1]


# A log mimicking the strlen/--enforce-contract case: stack frames pinned
# to the contract attribute line (88), violation actually at line 101 in
# the `Violated property:` block. Issue.file_path / line_number must
# resolve to line 101 via error_location, not line 88 via stack_trace[-1].
_CONTRACT_FAILURE_LOG = """ESBMC version 8.2.0 64-bit x86_64 linux
[Counterexample]


State 305 file string.c line 101 column 3 function strlen thread 0
----------------------------------------------------
Violated property:
  file string.c line 101 column 3 function strlen
Stack trace:
  __ESBMC_contracts_original_strlen at file string.c line 88 column 1
  c:@F@strlen at file string.c line 88 column 1
  dereference failure: array bounds violated
"""


@pytest.fixture
def contract_issue() -> VerifierIssue:
    """Parsed Issue from _CONTRACT_FAILURE_LOG via the real esbmc_spec."""
    return IssueSpecOutputParser(esbmc_spec).parse_output(_CONTRACT_FAILURE_LOG).issues[0]  # type: ignore[return-value]


@pytest.fixture
def deepest_first_issue() -> Issue:
    """Parsed Issue from _TWO_FRAME_LOG with deepest_first wrapping on (no
    error_location captured — this spec doesn't define one)."""
    spec = _spec_with_trace_order(deepest_first_wrapped=True)
    return IssueSpecOutputParser(spec).parse_output(_TWO_FRAME_LOG).issues[0]


def test_error_location_overrides_stack_trace(contract_issue: VerifierIssue) -> None:
    """When the spec captures error_location, file_path / line_number
    resolve to the violation site, not the stack trace's last frame."""
    assert contract_issue.error_location is not None
    assert contract_issue.error_location.line_idx == 100  # 0-based for line 101
    assert contract_issue.error_location.column_idx == 2  # 0-based for column 3
    assert str(contract_issue.error_location.path) == "string.c"

    # The location-bearing properties prefer error_location over stack_trace[-1].
    assert contract_issue.line_number == 101
    assert str(contract_issue.file_path) == "string.c"


def test_error_location_optional_falls_back_to_stack_trace(
    deepest_first_issue: Issue,
) -> None:
    """A spec without error_location leaves issue.error_location=None and
    properties fall back to the stack-trace last frame."""
    assert deepest_first_issue.error_location is None
    # With deepest_first, stack_trace[-1] is the deepest frame (line 99).
    assert deepest_first_issue.line_number == 99


def test_error_location_no_match_falls_back() -> None:
    """When the spec defines error_location but the regex doesn't match,
    error_location stays None and properties fall back to the stack trace."""
    log_without_violated_property = """ESBMC version 8.2.0 64-bit x86_64 linux
[Counterexample]


State 1 file demo.c line 50 column 1 function f thread 0
----------------------------------------------------
Stack trace:
  c:@F@f at file demo.c line 50 column 1
  assertion failed
"""
    parser = IssueSpecOutputParser(esbmc_spec)
    result = parser.parse_output(log_without_violated_property)

    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.error_location is None
    # Falls back to stack_trace[-1] (only one frame here, line 50).
    assert issue.line_number == 50


def test_function_name_skips_wrapper_frame_under_contracts(
    contract_issue: VerifierIssue,
) -> None:
    """Contract-instrumentation: stack_trace[-1] is the
    ``__ESBMC_contracts_original_*`` wrapper whose ``name`` regex doesn't
    resolve. function_name walks past it via the error_location path
    match instead of blindly returning the innermost name."""
    # Sanity-check the broken-looking shape we're correcting around.
    assert contract_issue.stack_trace[-1].name is None

    assert contract_issue.function_name == "strlen"
    # Agrees with file_path / line_number — internal consistency.
    assert str(contract_issue.file_path) == "string.c"
    assert contract_issue.line_number == 101


def test_function_name_falls_back_to_innermost_without_error_location(
    deepest_first_issue: Issue,
) -> None:
    """Verifiers without an error-location header get innermost-frame
    behavior — same as before the contract fix."""
    assert deepest_first_issue.error_location is None
    # Innermost frame is "inner" (deepest_first put line 99 at [-1]).
    assert deepest_first_issue.function_name == "inner"


def test_function_name_returns_none_on_empty_stack_trace() -> None:
    """Empty stack_trace + no error_location returns None, doesn't raise."""
    issue = Issue(
        error_type="assertion",
        message="x > 0",
        stack_trace=[],
        severity="error",
    )
    assert issue.function_name is None


def test_function_name_falls_back_when_no_frame_matches_error_location_path() -> None:
    """When error_location names a path no stack frame matches, the walk
    falls through to ``stack_trace[-1].name``. Regression guard against a
    future path-comparison tightening silently dropping the answer."""
    issue = Issue(
        error_type="assertion",
        message="x > 0",
        stack_trace=[
            ProgramTrace(
                trace_index=0,
                path=Path("frame_only.c"),
                name="caller",
                line_idx=10,
            ),
        ],
        severity="error",
        error_location=ErrorLocation(
            path=Path("violation_site.c"),  # not in any frame
            line_idx=42,
        ),
    )
    assert issue.function_name == "caller"
