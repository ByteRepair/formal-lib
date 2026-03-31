# Author: Yiannis Charalambous

from hashlib import sha256
from pathlib import Path
from typing import Any

from formal_lib.issue_parser import IssueRegexSpec, StackTraceRegexSpec


def _pytest_cache_properties(
    base_cmd: Path, sources: list[Path], timeout: int | None, cwd: Path
) -> Any:
    """Hash contents of all .py files for directory inputs."""
    hashes: list[str] = []
    for source in sources:
        if source.is_dir():
            for f in sorted(source.rglob("*.py")):
                hashes.append(sha256(f.read_bytes()).hexdigest())
        else:
            hashes.append(sha256(source.read_bytes()).hexdigest())
    return [str(base_cmd), timeout, hashes]


pytest_spec: IssueRegexSpec = IssueRegexSpec(
    # Detect pytest by its distinctive session header.
    detect=r"^={5,} test session starts ={5,}$",
    # Match both collection ERROR blocks and test FAILURE blocks
    # Test failure: "_____ test_name _____" (underscores, space, identifier, space, underscores)
    # Collection error: "_____ ERROR collecting path _____"
    # Block ends at next block header, pytest-regtest report, short test summary, or end of string
    # Note: Use \Z instead of $ to match only end of string (not end of line in MULTILINE mode)
    block=r"_{5,}\s+(?:ERROR collecting [^\n]+|\w+)\s+_{5,}\n.*?(?=_{5,}\s+(?:ERROR|\w+)\s+_{5,}|-{5,}\s+pytest-regtest|={5,}\s+short test summary|\Z)",
    # Extract error type from lines like "E   SyntaxError: invalid syntax" or "E   AssertionError"
    error_type=r"E\s+(\w+Error)",
    # Extract the error message after the error type (handles both "Error: msg" and "Error" alone)
    message=r"E\s+\w+Error:?\s*(.+?)$",
    # Severity is always "error" for pytest issues (collection errors and test failures)
    severity=r"(ERROR|FAILED)",
    stack_trace_spec=StackTraceRegexSpec(
        # Match all location lines: "path.py:line: in func" or "path.py:line: ErrorType"
        block=r"(?:^[^\s>E].+?\.py:\d+:.*$\n?)+",
        # Each trace entry is a single line in pytest (e.g., "tests/test_config.py:6: in <module>")
        trace_entry=r"^[^\s>E].+?\.py:\d+:.*$",
        # Individual trace index is implicit in pytest (order in stack)
        trace_index=r"^",  # Not applicable for pytest, using placeholder
        # Extract file path from lines like "tests/test_config.py:6: in <module>"
        path=r"([^\s:]+\.py):\d+:",
        # Extract function name from "in func_name" (may not exist in test failures)
        name=r":\s+in\s+(.+?)$",
        # Extract line number from lines like "tests/test_config.py:6:"
        line_index=r":(\d+):",
    ),
    cache_properties=_pytest_cache_properties,
)
