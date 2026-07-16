# Author: Yiannis Charalambous

import re

from formal_lib.specs.base import (
    CounterexampleRegexSpec,
    IssueRegexSpec,
    StackTraceRegexSpec,
    format_match,
    missing_hint,
)

cbmc_spec: IssueRegexSpec = IssueRegexSpec(
    # Detect CBMC by its version banner (e.g. "CBMC version 6.7.1 64-bit x86_64 linux").
    detect=r"^CBMC version \d+",
    success=r"^VERIFICATION SUCCESSFUL$",
    # Each "Trace for <id>:" section is an issue block.
    # With --stop-on-fail, CBMC uses "Counterexample:" instead of "Trace for <id>:".
    # Matches from the header to the next trace header, results summary, or end of string.
    block=missing_hint("Needs --trace")(
        r"(?:Trace for [^\n]+|Counterexample):\n.*?(?=Trace for [^\n]+:\n|Counterexample:\n|\*\* \d+ of \d+|\Z)"
    ),
    # Greedy (?s).* skips to LAST "Violated property:" in block (CBMC accumulates them).
    # Captures first word of description line: "assertion", "arithmetic", "array", etc.
    error_type=r"(?s).*Violated property:\n\s+[^\n]+\n\s+(\S+)",
    # Description + condition from last Violated property (condition line optional).
    message=format_match(
        lambda v: re.sub(r"\s*\n\s*", ". The Violated Property is: ", v)
    )(r"(?s).*Violated property:\n\s+[^\n]+\n\s+(.+?(?:\n\s+.+?)?)$"),
    # Always "error" — "Violated property" doesn't match IssueSeverities, triggers fallback.
    severity=r"(Violated property)",
    stack_trace_spec=StackTraceRegexSpec(
        # Match the last "Violated property:" section in the block. Negative lookahead
        # ensures no subsequent VP exists (CBMC accumulates VPs from previous traces).
        # _parse_traces uses re.MULTILINE only for stack traces (no DOTALL), so [\s\S]*
        # is used in the lookahead to span newlines.
        block=r"Violated property:\n\s+file\s+\S+\s+function\s+.+?\s+line\s+\d+[^\n]*(?![\s\S]*Violated property:)",
        # Anchored to line start to avoid matching State header lines.
        trace_entry=r"^\s+file\s+\S+\s+function\s+.+?\s+line\s+\d+[^\n]*",
        trace_index=r"^",
        path=r"file\s+(\S+)",
        # Non-greedy up to " line " so names containing spaces are captured whole
        # (CBMC C++ demangled templates; Rust generics like `foo::<'_, i32>` via Kani).
        name=r"function\s+(.+?)\s+line",
        line_index=r"line\s+(\d+)",
    ),
    counterexample_spec=CounterexampleRegexSpec(
        # States between trace header and first "Violated property:".
        block=r"(?:Trace for [^\n]+|Counterexample):\n(.*?)(?=Violated property:|\Z)",
        # Each state entry: header + separator + assignment.
        trace_entry=r"State\s+\d+\s+file\s+\S+\s+function\s+.+?\s+line\s+\d+[^\n]*thread\s+\d+\n[-]+\n.*?(?=\nState\s|\nViolated|\n\n|\Z)",
        trace_index=r"State\s+(\d+)",
        path=r"file\s+(\S+)",
        # Non-greedy up to " line " so names containing spaces are captured whole
        # (CBMC C++ demangled templates; Rust generics like `foo::<'_, i32>` via Kani).
        name=r"function\s+(.+?)\s+line",
        line_index=r"line\s+(\d+)",
        # Require at least one char so states with no assignment return None.
        assignment=r"\n[-]+\n(.+)",
    ),
)
