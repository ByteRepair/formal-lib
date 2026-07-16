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

# A PASSING harness in old format with reachability checks enabled. Every real
# check is SUCCESS, but the injected reachability_check "fails" (the assertion is
# reachable), so CBMC prints `VERIFICATION FAILED`. The verdict must come from the
# real per-check statuses, not that misleading line.
_OLD_FMT_PASS_REACH_ON = """Kani Rust Verifier 0.67.0 (standalone)
Checking harness check_ok...
CBMC version 6.8.0 (cbmc-6.8.0) 64-bit x86_64 linux

** Results:
/src/ok.rs function check_ok
[check_ok.assertion.1] line 5 [KANI_CHECK_ID_ok::ok_0] assertion failed: x == y: SUCCESS
[check_ok.reachability_check.1] line 5 KANI_CHECK_ID_ok::ok_0: FAILURE

Trace for check_ok.reachability_check.1:

State 1 file /src/ok.rs function check_ok line 5 thread 0
----------------------------------------------------
  var=1 (00000001)

Violated property:
  file /src/ok.rs function check_ok line 5 thread 0
  KANI_CHECK_ID_ok::ok_0
  FALSE


** 1 of 2 failed (2 iterations)
VERIFICATION FAILED
Manual Harness Summary:
Verification failed for - check_ok
Complete - 0 successfully verified harnesses, 1 failures, 1 total.
"""


# Old format with an uppercase property class (`NaN`) as its only failure. Guards
# against a class charset too narrow to match it — which would both mislabel the
# error_type and (via the shared verdict pattern) misreport the run as passing.
_OLD_FMT_NAN_FAIL = """Kani Rust Verifier 0.67.0 (standalone)
CBMC version 6.8.0 (cbmc-6.8.0) 64-bit x86_64 linux

** Results:
/src/nan.rs function check_nan
[check_nan.NaN.1] line 6 NaN on + in x + y: FAILURE

Trace for check_nan.NaN.1:

State 21 file /src/nan.rs function check_nan line 6 thread 0
----------------------------------------------------
  x=0.0f (00000000 00000000 00000000 00000000)

Violated property:
  file /src/nan.rs function check_nan line 6 thread 0
  NaN on + in x + y
  !(var_2 != FALSE)


** 1 of 1 failed (1 iterations)
VERIFICATION FAILED
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


def test_uppercase_property_class_and_verdict() -> None:
    """An uppercase class (`NaN`) must be captured as the error_type, and a run
    whose only failure is such a check must be reported as failed — the class
    charset feeds both error_type and the verdict pattern."""
    result = _parse(_OLD_FMT_NAN_FAIL)

    assert result.successful is False
    assert len(result.issues) == 1
    assert result.issues[0].error_type == "NaN"


def test_reachability_check_is_neither_an_issue_nor_a_failure() -> None:
    """A run whose only failing property is a reachability_check has passed: the
    probe "fails" precisely because the assertion is reachable. It must not surface
    as an issue (block lookahead) nor flip the verdict (success lookahead)."""
    reachability_only = _OLD_FMT_FAILURE.replace(
        "check_overflow.assertion.1", "check_overflow.reachability_check.1"
    )
    result = _parse(reachability_only)

    assert result.successful is True
    assert result.issues == []


def test_passing_harness_with_reachability_probe_is_successful() -> None:
    """With reachability checks enabled, a passing harness still prints
    `VERIFICATION FAILED` in old format. The verdict must be read from the real
    per-check statuses (all SUCCESS) and reported as successful, with no issues."""
    result = _parse(_OLD_FMT_PASS_REACH_ON)

    assert result.successful is True
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
    """A passing native-format run has no `VERIFICATION:- FAILED` line and no
    failing Results check, so it is recognised as successful and must not
    spuriously emit the hint."""
    result = _parse(_NATIVE_FMT_SUCCESS)

    assert result.successful is True
    assert result.issues == []
    assert result.hints == []
