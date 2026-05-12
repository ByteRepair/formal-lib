# Author: Yiannis Charalambous

from formal_lib.specs.base import (
    CounterexampleRegexSpec,
    ErrorLocationRegexSpec,
    IssueRegexSpec,
    StackTraceRegexSpec,
    deepest_first,
    missing_hint,
    try_patterns,
)

# A single ESBMC stack-trace frame line. Matches both shapes:
#   "  c:@F@<sym> at file <path> line <N> column <N> [function <fn>]"
#   "  __ESBMC_contracts_original_<sym> at file <path> ..."
# The discriminator is the literal " at file " — every frame has it, no
# description line does (description lines are categories like "Same object
# violation" or "dereference failure: array bounds violated"). Skipping on
# this token cleanly separates frames from descriptions regardless of the
# symbol prefix ESBMC uses.
_FRAME_LINE = r"[ \t]+\S+ at file [^\n]*\n"

# Negative lookahead used at the start of a description-line capture.
# Without it, the engine can backtrack the greedy frame-skip and capture
# a frame line as the description (e.g. on strlen-style output, the
# engine would skip 1 frame and capture "c:@F@strlen at file ..." rather
# than skipping both frames and capturing "dereference failure: array
# bounds violated"). The lookahead forbids " at file " in the current
# line, so the description capture can only succeed on a real
# description line.
_NOT_FRAME = r"(?![^\n]* at file )"

# The "Violated property:" block prefix, shared by error_type / message
# fallbacks and the dedicated error_location spec. Captures the
# "Violated property:" header and its indented file/line description line
# (the part that's always present, regardless of show-stacktrace).
_VIOLATED_PROP_HEADER = (
    r"Violated property:\n[ \t]+file\s+\S+\s+line\s+\d+[^\n]*"
)

# Prefix that skips frame lines and lands on the Nth description line.
# N=1 (first description line) is the error_type target;
# N=2 (skip one description line, capture the next) is the message target.
# ``[ \t]+`` between lines (rather than ``\s+``) prevents skipping blank
# lines — ``\s`` would jump past a blank line to an unrelated line like
# ``VERIFICATION FAILED`` and capture it as the message.
def _description_pattern(*, after_stack_trace: bool, line_offset: int) -> str:
    """Build a regex that lands on a specific description line.

    ``after_stack_trace=True`` skips frames under ``Stack trace:`` (the
    --show-stacktrace shape); ``False`` anchors on ``Violated property:``
    (the no-show-stacktrace shape). ``line_offset`` is 1 for the first
    description line (the error category), 2 for the second (the
    condition / message under a multi-line category).
    """
    if after_stack_trace:
        prefix = r"Stack trace:\n(?:" + _FRAME_LINE + r")*"
    else:
        prefix = _VIOLATED_PROP_HEADER + r"\n"
    # Skip (line_offset - 1) description lines, then capture the next.
    skip = (r"[ \t]+" + _NOT_FRAME + r"[^\n]+\n") * (line_offset - 1)
    return prefix + skip + r"[ \t]+" + _NOT_FRAME + r"([^\n]+?)[ \t]*$"


esbmc_spec: IssueRegexSpec = IssueRegexSpec(
    # Detect ESBMC by its version banner (e.g. "ESBMC version 8.1.0 64-bit x86_64 linux").
    detect=r"^ESBMC version \d+",
    success=r"^VERIFICATION SUCCESSFUL$",
    # Each [Counterexample] section is an issue block.
    # Matches from [Counterexample] to the next one or end of string.
    block=r"\[Counterexample\].*?(?=\[Counterexample\]|\Z)",
    # ESBMC prints the error description in two different places depending
    # on --show-stacktrace. Primary captures from the Stack trace section
    # (the production hot path — contractor always passes the flag); the
    # fallback captures the same data inline under "Violated property:"
    # when the flag isn't set. error_type = first description line,
    # message = second (empty when the category has no follow-on line).
    error_type=try_patterns(
        _description_pattern(after_stack_trace=True, line_offset=1),
        _description_pattern(after_stack_trace=False, line_offset=1),
    ),
    message=try_patterns(
        _description_pattern(after_stack_trace=True, line_offset=2),
        _description_pattern(after_stack_trace=False, line_offset=2),
    ),
    # ESBMC issues are always errors.
    severity=r"(Violated property)",
    stack_trace_spec=StackTraceRegexSpec(
        # Stack trace section: "Stack trace:" followed by indented lines.
        block=missing_hint("Needs --show-stacktrace")(
            r"Stack trace:\n(?:\s+[^\n]+\n)*"
        ),
        # Full lines containing "file <path> line <num>", including any c:@ prefix.
        # ESBMC prints frames deepest-first; deepest_first() reverses the
        # captured list so stack_trace[-1] is the failure frame.
        trace_entry=deepest_first()(
            r"^[^\n]*\bfile\s+\S+\s+line\s+\d+[^\n]*"
        ),
        trace_index=r"^",
        path=r"file\s+(\S+)",
        # Extract callee symbol from c:@<letter>@ prefix (e.g. c:@F@main).
        name=r"c:@\w@(\S+)",
        line_index=r"line\s+(\d+)",
    ),
    # The "Violated property:" header carries the canonical violation site.
    # Under contract instrumentation (--enforce-contract), the visible stack
    # frames collapse to the contract-attribute line; the deref location
    # only appears here. Issue.file_path / line_index prefer this when set.
    error_location=ErrorLocationRegexSpec(
        block=_VIOLATED_PROP_HEADER,
        path=r"file\s+(\S+)",
        line_index=r"line\s+(\d+)",
        column_index=r"column\s+(\d+)",
    ),
    counterexample_spec=CounterexampleRegexSpec(
        # Counterexample block: from [Counterexample] to Violated property.
        block=r"\[Counterexample\]\n(.*?)(?=Violated property:|\Z)",
        # Each state entry: header + separator + assignment (stops at next state or section).
        trace_entry=r"State\s+\d+\s+file\s+\S+\s+line\s+\d+[^\n]*thread\s+\d+\n[-]+\n.*?(?=\nState\s|\nViolated|\n\n|\Z)",
        trace_index=r"State\s+(\d+)",
        path=r"file\s+(\S+)",
        name=r"function\s+(\S+)",
        line_index=r"line\s+(\d+)",
        # Require at least one char so states with no assignment return None.
        assignment=r"\n[-]+\n(.+)",
    ),
)
