# Author: Yiannis Charalambous

"""Tests for the Kani spec.

Kani drives CBMC, so `kani --output-format old --cbmc-args --trace` emits CBMC's
own output and kani_spec is cbmc_spec with a few overrides. These tests pin the
Kani-specific behaviour: detecting Kani ahead of CBMC, the missing-flag hint when
Kani is run in its native (non-old) format, dropping the reachability_check
properties Kani injects, and stripping the KANI_CHECK_ID marker from messages.
"""

from formal_lib import IssueSpecOutputParser
from formal_lib.issue import VerifierIssue
from formal_lib.specs import cbmc_spec, detect_spec, kani_spec


# `kani --output-format old --cbmc-args --trace` on a failing overflow harness.
_OLD_FMT_FAILURE = """Kani Rust Verifier 0.67.0 (standalone)
Checking harness check_overflow...
CBMC version 6.8.0 (cbmc-6.8.0) 64-bit x86_64 linux

** Results:
/src/overflow.rs function check_overflow
[check_overflow.assertion.1] line 5 attempt to add with overflow: FAILURE

Trace for check_overflow.assertion.1:

State 21 file /src/overflow.rs function check_overflow line 3 thread 0
----------------------------------------------------
  x=255 (11111111)

State 40 file /src/overflow.rs function check_overflow line 5 thread 0
----------------------------------------------------
  var_4.1=TRUE (00000001)

Violated property:
  file /src/overflow.rs function check_overflow line 5 thread 0
  attempt to add with overflow
  !(var_4.1 != FALSE)


** 1 of 1 failed (2 iterations)
VERIFICATION FAILED
"""

# Kani's native (regular) format — no CBMC trace. Uses the `VERIFICATION:-`
# success line and Check blocks the old-format parser can't read.
_NATIVE_FMT_FAILURE = """Kani Rust Verifier 0.67.0 (standalone)
Checking harness check_foo...

RESULTS:
Check 1: check_foo.assertion.1
\t - Status: FAILURE
\t - Description: "assertion failed: x < 10"
\t - Location: src/lib.rs:5:5 in function check_foo


SUMMARY:
 ** 1 of 1 failed

VERIFICATION:- FAILED
"""

_NATIVE_FMT_SUCCESS = """Kani Rust Verifier 0.67.0 (standalone)
Checking harness check_foo...

RESULTS:
Check 1: check_foo.assertion.1
\t - Status: SUCCESS
\t - Description: "assertion failed: x < 10"


SUMMARY:
 ** 0 of 1 failed

VERIFICATION:- SUCCESSFUL
"""


def _parse(log: str):
    return IssueSpecOutputParser(kani_spec).parse_output(log)


def test_detect_prefers_kani_over_cbmc() -> None:
    """Old-format output carries a `CBMC version` banner too, so cbmc_spec.detect
    also matches it — auto-detect must return kani_spec because it is registered
    first."""
    assert detect_spec(_OLD_FMT_FAILURE) is kani_spec
    # Sanity: cbmc_spec would indeed have claimed it on its own.
    import re

    assert re.search(cbmc_spec.detect, _OLD_FMT_FAILURE, re.MULTILINE)


def test_old_format_failure_parses_issue() -> None:
    """The happy path: one assertion issue with message, location, counterexample."""
    result = _parse(_OLD_FMT_FAILURE)

    assert result.successful is False
    assert len(result.issues) == 1
    issue = result.issues[0]

    assert issue.error_type == "assertion"
    assert issue.message == (
        "attempt to add with overflow. The Violated Property is: !(var_4.1 != FALSE)"
    )
    # Failure site comes from the Violated property location.
    assert issue.function_name == "check_overflow"
    assert issue.line_number == 5
    assert str(issue.file_path) == "/src/overflow.rs"

    # Counterexample carries the CBMC state assignments.
    assert isinstance(issue, VerifierIssue)
    assignments = [t.assignment for t in issue.counterexample]
    assert "x=255 (11111111)" in assignments
    assert "var_4.1=TRUE (00000001)" in assignments


def test_error_type_is_property_class_from_trace_header() -> None:
    """Kani lowers everything to CBMC assertions; error_type is the property class
    read from the `Trace for <fn>.<class>.<n>:` header, not CBMC's first-word rule."""
    assert _parse(_OLD_FMT_FAILURE).issues[0].error_type == "assertion"


def test_reachability_check_traces_are_dropped() -> None:
    """Kani injects reachability_check properties (hidden in its native output).
    They must not surface as issues."""
    reachability_only = _OLD_FMT_FAILURE.replace(
        "check_overflow.assertion.1", "check_overflow.reachability_check.1"
    )
    result = _parse(reachability_only)

    assert result.successful is False
    assert result.issues == []


def test_kani_check_id_marker_stripped_from_message() -> None:
    """With reachability checks enabled Kani prefixes the description with a
    `[KANI_CHECK_ID_...]` marker; the message must not contain it."""
    with_marker = _OLD_FMT_FAILURE.replace(
        "  attempt to add with overflow\n",
        "  [KANI_CHECK_ID_overflow.57bbd1ec::overflow_0] attempt to add with overflow\n",
    )
    message = _parse(with_marker).issues[0].message

    assert "KANI_CHECK_ID" not in message
    assert message.startswith("attempt to add with overflow")


def test_native_format_failure_emits_flag_hint() -> None:
    """Run in Kani's native format, there is no CBMC trace to parse — the parser
    reports failure with no issues and surfaces the flag hint (mirrors CBMC's
    --trace hint)."""
    result = _parse(_NATIVE_FMT_FAILURE)

    assert result.successful is False
    assert result.issues == []
    assert result.hints == ["Needs --output-format old --cbmc-args --trace"]


def test_native_format_success_is_successful_without_hint() -> None:
    """A passing native-format run must be recognised as successful (the success
    pattern matches both `VERIFICATION:- SUCCESSFUL` and old-format
    `VERIFICATION SUCCESSFUL`) and must not spuriously emit the hint."""
    result = _parse(_NATIVE_FMT_SUCCESS)

    assert result.successful is True
    assert result.issues == []
    assert result.hints == []
