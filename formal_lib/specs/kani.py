# Author: Yiannis Charalambous

import re
from dataclasses import replace

from formal_lib.specs.base import format_match, missing_hint
from formal_lib.specs.cbmc import cbmc_spec


def _kani_message(value: str) -> str:
    """CBMC's message formatting, then drop Kani's internal check-id marker.

    Kani lowers every check into a CBMC assertion whose description is prefixed
    with a ``[KANI_CHECK_ID_<crate>.<hash>::<name>]`` marker (e.g.
    ``[KANI_CHECK_ID_overflow...] attempt to add with overflow``). Reuse CBMC's
    "description. The Violated Property is: <condition>" formatting, then strip
    the marker so the message reads like the rest of the library's output.
    """
    value = re.sub(r"\s*\n\s*", ". The Violated Property is: ", value)
    return re.sub(r"\[KANI_CHECK_ID_[^\]]*\]\s*", "", value)


# Kani drives CBMC under the hood, so `kani --output-format old --cbmc-args --trace`
# emits CBMC's own output: the `Trace for <id>:` blocks, `State ... / assignment`
# counterexample states, and `Violated property:` sections are byte-for-byte the CBMC
# format. kani_spec is therefore cbmc_spec with only the handful of Kani-specific
# differences overridden — the stack-trace, counterexample, and severity parsing are
# reused verbatim. This keeps a single source of truth: fixing the CBMC trace parser
# fixes it for Kani too. (Kani must be registered before cbmc in SPECS, because Kani's
# output also contains a `CBMC version` banner that cbmc_spec.detect would match.)
kani_spec = replace(
    cbmc_spec,
    # Kani prints its own banner above CBMC's; detect on that.
    detect=r"^Kani Rust Verifier",
    # Derive the verdict from the per-check statuses in CBMC's `** Results:` section,
    # NOT the top-line `VERIFICATION` verdict. In old format Kani does not post-process
    # its assertion-reachability probes, so a *passing* run still prints `VERIFICATION
    # FAILED`: each `reachability_check` property "fails" precisely because the assertion
    # is reachable (normal). Keying off the real per-check statuses lets Kani keep
    # reachability checks enabled — they catch unreachable, vacuously-passing assertions,
    # so disabling them would weaken verification — while still reporting correctly.
    #
    # negate_success: a match means FAILURE. A real failure is either a `** Results:`
    # line for a non-`reachability_check` check with status FAILURE, or the native-format
    # `VERIFICATION:- FAILED` line (native format has no such Results lines and is already
    # correctly post-processed by Kani, so its verdict line is trustworthy).
    success=(
        r"^\[[^\]]*\.(?!reachability_check\.)[A-Za-z][\w-]*\.\d+\][^\n]*: FAILURE$"
        r"|^VERIFICATION:- FAILED$"
    ),
    negate_success=True,
    # Same trace-block boundaries as CBMC, with two Kani adjustments:
    #  * skip the `reachability_check` properties Kani injects (its native format
    #    hides them; they are not real bugs), and
    #  * annotate the block so that when no trace is present — i.e. Kani was run in
    #    its native format, or in old format without `--trace` — the parser surfaces
    #    a hint telling the user which flags expose the counterexample, mirroring
    #    CBMC's `--trace` hint.
    block=missing_hint("Needs --output-format old --cbmc-args --trace")(
        r"(?:Trace for (?!\S+\.reachability_check\.)[^\n]+|Counterexample):\n"
        r".*?(?=Trace for [^\n]+:\n|Counterexample:\n|\*\* \d+ of \d+|\Z)"
    ),
    # Kani lowers every check to an assertion, so CBMC's first-word-of-description
    # heuristic is unhelpful. The useful category is the property class at the end of
    # the trace header, e.g. `Trace for check_overflow.assertion.1:` -> "assertion".
    # Use a greedy `.+` (not `\S+`) so it spans function names that contain spaces and
    # angle brackets, e.g. `Trace for kani::...::offset::<i32, *const i32,
    # isize>.safety_check.1:` -> "safety_check". The class charset allows uppercase and
    # hyphens for CBMC-style classes such as `NaN` and `division-by-zero`.
    error_type=r"Trace for .+\.([A-Za-z][\w-]*)\.\d+:",
    # Reuse CBMC's "last Violated property" capture (Kani emits a second, readable
    # Violated property block per assertion), then strip the KANI_CHECK_ID marker.
    message=format_match(_kani_message)(
        r"(?s).*Violated property:\n\s+[^\n]+\n\s+(.+?(?:\n\s+.+?)?)$"
    ),
)
