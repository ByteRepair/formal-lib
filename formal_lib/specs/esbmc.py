# Author: Yiannis Charalambous

from formal_lib.issue_parser import (
    CounterexampleRegexSpec,
    IssueRegexSpec,
    StackTraceRegexSpec,
)

esbmc_spec: IssueRegexSpec = IssueRegexSpec(
    # Each [Counterexample] section is an issue block.
    # Matches from [Counterexample] to the next one or end of string.
    block=r"\[Counterexample\].*?(?=\[Counterexample\]|\Z)",
    # Error type from "Stack trace:" section — skip c:@ symbol lines,
    # take text before the first colon on the error description line.
    error_type=r"Stack trace:\n(?:\s+c:@\S*[^\n]*\n)*\s+([^:\n]+):",
    # Error message — text after the colon on the same line.
    message=r"Stack trace:\n(?:\s+c:@\S*[^\n]*\n)*\s+[^:\n]+:\s*(.+?)$",
    # ESBMC issues are always errors.
    severity=r"(Violated property)",
    stack_trace_spec=StackTraceRegexSpec(
        # Stack trace section: "Stack trace:" followed by indented lines,
        # plus "Violated property:" location line before it.
        block=r"(?:Violated property:\n\s+file[^\n]+\n|Stack trace:\n(?:\s+[^\n]+\n)*)",
        # Individual trace entries: lines containing "at file ... line ... function ..."
        # or the violated property location line "file ... line ... function ..."
        trace_entry=r"(?:at\s+)?file\s+(\S+)\s+line\s+(\d+)[^\n]*function\s+(\S+)",
        trace_index=r"^",
        path=r"file\s+(\S+)",
        name=r"function\s+(\S+)",
        line_index=r"line\s+(\d+)",
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
        assignment=r"\n[-]+\n(.*)",
    ),
)
