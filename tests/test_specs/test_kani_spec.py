# Author: Yiannis Charalambous

"""Unit tests for Kani-specific behaviour the regression suite can't express.

kani_spec's parsing, verdict, and field extraction are covered end-to-end by the
data-driven fixtures in tests/regressions/samples/kani/ (real `kani --output-format
old --cbmc-args --trace` logs paired with expected JSON) — including the NaN class,
spaced generic function names, reachability handling, and KANI_CHECK_ID stripping.
What remains here is only what has no JSON representation: auto-detection (the
regression runner always passes an explicit --backend) and the missing-flag hint
(hints are excluded from serialized output).
"""

from formal_lib import IssueSpecOutputParser
from formal_lib.specs import cbmc_spec, detect_spec, kani_spec


# An old-format failure carries both a `Kani Rust Verifier` and a `CBMC version`
# banner, so both specs' detect patterns match it.
_OLD_FMT_FAILURE = """Kani Rust Verifier 0.67.0 (standalone)
Checking harness check_overflow...
CBMC version 6.8.0 (cbmc-6.8.0) 64-bit x86_64 linux

** Results:
/src/overflow.rs function check_overflow
[check_overflow.assertion.1] line 5 attempt to add with overflow: FAILURE

** 1 of 1 failed (2 iterations)
VERIFICATION FAILED
"""

# Kani's native (regular) format — no CBMC trace. Failure uses `VERIFICATION:- FAILED`
# and Check blocks the old-format parser can't read.
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
    first. Not expressible as a regression fixture: that runner always passes an
    explicit --backend."""
    import re

    assert detect_spec(_OLD_FMT_FAILURE) is kani_spec
    # Sanity: cbmc_spec would indeed have claimed it on its own.
    assert re.search(cbmc_spec.detect, _OLD_FMT_FAILURE, re.MULTILINE)


def test_native_format_failure_emits_flag_hint() -> None:
    """Run in Kani's native format there is no CBMC trace to parse — the parser
    reports failure with no issues and surfaces the flag hint (mirrors CBMC's
    --trace hint). Hints are excluded from serialized output, so this can't be a
    regression fixture."""
    result = _parse(_NATIVE_FMT_FAILURE)

    assert result.successful is False
    assert result.issues == []
    assert result.hints == ["Needs --output-format old --cbmc-args --trace"]


def test_native_format_success_is_successful_without_hint() -> None:
    """A passing native-format run has no `VERIFICATION:- FAILED` line and no failing
    Results check, so it is successful and must not spuriously emit the hint."""
    result = _parse(_NATIVE_FMT_SUCCESS)

    assert result.successful is True
    assert result.issues == []
    assert result.hints == []
