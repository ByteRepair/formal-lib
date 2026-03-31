# Author: Yiannis Charalambous

from formal_lib.issue_parser import (
    CounterexampleRegexSpec,
    IssueRegexSpec,
    StackTraceRegexSpec,
)

esbmc_spec: IssueRegexSpec = IssueRegexSpec(
    # Detect ESBMC by its version banner (e.g. "ESBMC version 8.1.0 64-bit x86_64 linux").
    detect=r"^ESBMC version \d+",
    # Each [Counterexample] section is an issue block.
    # Matches from [Counterexample] to the next one or end of string.
    block=r"\[Counterexample\].*?(?=\[Counterexample\]|\Z)",
    # Error type from "Stack trace:" section — skip c:@ symbol lines,
    # first word on the error description line (e.g. "assertion").
    error_type=r"Stack trace:\n(?:\s+c:@\S*[^\n]*\n)*\s+(\S+)",
    # Error message — everything after the first word on the same line.
    message=r"Stack trace:\n(?:\s+c:@\S*[^\n]*\n)*\s+\S+\s+(.+?)$",
    # ESBMC issues are always errors.
    severity=r"(Violated property)",
    stack_trace_spec=StackTraceRegexSpec(
        # Stack trace section: "Stack trace:" followed by indented lines.
        block=r"Stack trace:\n(?:\s+[^\n]+\n)*",
        # Full lines containing "file <path> line <num>", including any c:@ prefix.
        trace_entry=r"^[^\n]*\bfile\s+\S+\s+line\s+\d+[^\n]*",
        trace_index=r"^",
        path=r"file\s+(\S+)",
        # Extract callee symbol from c:@<letter>@ prefix (e.g. c:@F@main).
        name=r"c:@\w@(\S+)",
        line_index=r"line\s+(\d+)",
        missing="Needs --show-stacktrace",
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
