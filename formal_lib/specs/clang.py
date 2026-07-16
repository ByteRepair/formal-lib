# Author: Yiannis Charalambous

from formal_lib.specs.base import IssueRegexSpec, StackTraceRegexSpec

clang_spec: IssueRegexSpec = IssueRegexSpec(
    # Detect clang/gcc diagnostics by the "file:line:col: error/warning:" pattern.
    detect=r"^[^\s:]+:\d+:\d+:\s+(?:error|warning):",
    # No positive success signal (a clean compile is silent), so the verdict is the
    # failure pattern — an `error:` diagnostic — plus the parser's error-issue
    # baseline. Warnings are issues but never fail the build.
    failure=r":\d+:\s+error:",
    # Each diagnostic is a block: "file:line:col: type: message\n<source>\n<indicator>"
    # Match the diagnostic line plus optional following source/indicator lines.
    block=r"^[^\s:]+:\d+:\d+:\s+(?:error|warning):[^\n]*\n(?:[^\n]*\n[^\s:]*[~^ ]*\n?)?",
    # Extract error type: "error" or "warning" from "file:line:col: error: message"
    error_type=r":\d+:\s+(error|warning):",
    # Extract message after "error: " or "warning: "
    message=r":\d+:\s+(?:error|warning):\s+(.+?)$",
    # Severity: "error" or "warning"
    severity=r":\d+:\s+(error|warning):",
    stack_trace_spec=StackTraceRegexSpec(
        # The entire diagnostic line is the stack trace block
        block=r"^[^\s:]+:\d+:\d+:\s+(?:error|warning):[^\n]*$",
        # Single trace entry: the diagnostic line itself
        trace_entry=r"^([^\s:]+):(\d+):(\d+):\s+(?:error|warning):.*$",
        trace_index=r"^",
        path=r"^([^\s:]+):\d+:",
        name=r"^",  # Clang diagnostics don't include function names
        line_index=r"^[^\s:]+:(\d+):",
    ),
)
