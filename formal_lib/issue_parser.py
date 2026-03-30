# Author: Yiannis Charalambous

"""Regex-based parser for extracting structured issues from verifier output."""

import re
from typing import Any, Protocol, override, cast
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import Field

from formal_lib.program_trace import ProgramTrace, CounterexampleProgramTrace
from formal_lib.verifier_output import VerifierOutput
from formal_lib.issue import Issue, IssueSeverities, VerifierIssue


class IssueSpecOutput(VerifierOutput):
    """Verifier output that works with issue specs."""

    exit_success: int = Field(default=0)
    """Code for successful exit."""

    @property
    @override
    def successful(self) -> bool:
        """Returns true if return code matches success return code."""
        return self.return_code == self.exit_success


@dataclass
class StackTraceRegexSpec:
    """
    Regex specification for parsing stack traces within an issue.

    The hierarchy is:
    1. `block` - Selects the entire stack trace block from within an issue
    2. `trace_entry` - Matches individual trace entries within the block
    3. Individual field patterns extract properties from each trace entry
    """

    block: str
    """Regex pattern to select the entire stack trace block within an issue."""
    trace_entry: str
    """Regex pattern to match individual trace entries within the block.
    Each entry may span multiple lines (e.g., GCC shows source snippets)."""
    trace_index: str
    """Regex pattern to extract the trace position/index from a trace entry."""
    path: str
    """Regex pattern to extract the file path from a trace entry."""
    name: str
    """Regex pattern to extract the function/symbol name from a trace entry."""
    line_index: str
    """Regex pattern to extract the line number from a trace entry."""


@dataclass
class CounterexampleRegexSpec(StackTraceRegexSpec):
    """
    Regex specification for parsing counterexample traces within an issue.

    Extends StackTraceRegexSpec with an assignment pattern for extracting
    variable assignments from counterexample state entries.
    """

    assignment: str = ""
    """Regex pattern to extract the variable assignment from a trace entry."""


class CachePropertiesFn(Protocol):
    """Protocol for computing cache properties from verify_source args."""

    def __call__(
        self,
        base_cmd: Path,
        sources: list[Path],
        timeout: int | None,
        cwd: Path,
    ) -> Any: ...


@dataclass
class IssueRegexSpec:
    """
    Regex specification for parsing individual issues from verifier output.

    The hierarchy is:
    1. `block` - Selects individual issue blocks from the entire output
    2. Individual field patterns extract properties from within each issue block
    3. `stack_trace_spec` - Nested spec for parsing stack traces within the issue
    4. `counterexample_spec` - Optional nested spec for parsing counterexamples
    """

    block: str
    """Regex pattern to select individual issue blocks from the verifier output."""
    error_type: str
    """Regex pattern to extract the error type (e.g., 'TypeError', 'AssertionError')."""
    message: str
    """Regex pattern to extract the error message/description."""
    stack_trace_spec: StackTraceRegexSpec
    """Nested specification for parsing the stack trace within this issue."""
    severity: str
    """Regex pattern to extract the severity level (e.g., 'error', 'warning', 'info')."""
    counterexample_spec: CounterexampleRegexSpec | None = None
    """Optional nested specification for parsing counterexample traces."""
    cache_properties: CachePropertiesFn | None = field(default=None)
    """Optional function to compute cache properties from verify_source args.
    When None, default properties are used."""


class IssueSpecOutputParser:
    """
    Oracle output parser using regex. Defines the following regex field hierarchy:
    * Issue start
    * Issue severity, issue error type, issue message, issue stack trace

    Need to figure out correct way to express this...
    """

    def __init__(self, regex_spec: IssueRegexSpec) -> None:
        self.regex_spec: IssueRegexSpec = regex_spec

    def parse_output(
        self, exit_success: int, return_code: int, duration: float, output: str
    ) -> VerifierOutput:
        # Extract all issue blocks from the output
        issue_blocks: list[str] = []
        for match in re.finditer(
            self.regex_spec.block, output, re.DOTALL | re.MULTILINE
        ):
            issue_blocks.append(match.group(0))

        # Parse each issue block to extract individual issues
        issues: list[Issue] = [self._parse_issue(block) for block in issue_blocks]

        return IssueSpecOutput(
            exit_success=exit_success,
            return_code=return_code,
            issues=issues,
            output=output,
            duration=duration,
        )

    @staticmethod
    def _parse_traces(
        text: str,
        spec: StackTraceRegexSpec,
        *,
        as_counterexample: bool = False,
    ) -> list[ProgramTrace]:
        """Parse trace entries from text using a StackTraceRegexSpec.

        When as_counterexample is True and spec is a CounterexampleRegexSpec,
        produces CounterexampleProgramTrace with assignment data.
        """
        flags = re.DOTALL | re.MULTILINE if as_counterexample else re.MULTILINE
        block_match = re.search(spec.block, text, flags)
        if not block_match:
            return []

        block_text = block_match.group(0)
        traces: list[ProgramTrace] = []

        for trace_index, entry_match in enumerate(
            re.finditer(spec.trace_entry, block_text, flags)
        ):
            entry_text = entry_match.group(0)

            path_match = re.search(spec.path, entry_text)
            line_idx_match = re.search(spec.line_index, entry_text)
            if not (path_match and line_idx_match):
                continue

            name_match = re.search(spec.name, entry_text)
            path = Path(path_match.group(1))
            name = name_match.group(1) if name_match else None
            line_idx = int(line_idx_match.group(1)) - 1  # Convert to 0-based

            if (
                as_counterexample
                and isinstance(spec, CounterexampleRegexSpec)
                and spec.assignment
            ):
                assignment_match = re.search(
                    spec.assignment,
                    entry_text,
                    re.DOTALL,
                )
                assignment = (
                    assignment_match.group(1).strip() if assignment_match else None
                )
                traces.append(
                    CounterexampleProgramTrace(
                        trace_index=trace_index,
                        path=path,
                        name=name,
                        line_idx=line_idx,
                        assignment=assignment,
                    )
                )
            else:
                traces.append(
                    ProgramTrace(
                        trace_index=trace_index,
                        path=path,
                        name=name,
                        line_idx=line_idx,
                    )
                )

        return traces

    def _parse_issue(self, issue_text: str) -> Issue:
        """Function that parses a single issue and returns it."""

        # Extract error type
        error_type_match = re.search(
            self.regex_spec.error_type, issue_text, re.MULTILINE
        )
        error_type = error_type_match.group(1) if error_type_match else "Unknown"

        # Extract message
        message_match = re.search(self.regex_spec.message, issue_text, re.MULTILINE)
        message = message_match.group(1) if message_match else ""

        # Extract severity
        severity_match = re.search(self.regex_spec.severity, issue_text, re.MULTILINE)
        severity_str = severity_match.group(1).lower() if severity_match else "error"
        # Convert to valid severity literal
        if severity_str not in IssueSeverities:
            severity_str = "error"
        # Type cast after validation
        severity: IssueSeverities = cast(IssueSeverities, severity_str)

        # Extract stack trace
        stack_trace: list[ProgramTrace] = self._parse_traces(
            issue_text,
            self.regex_spec.stack_trace_spec,
        )

        # Ensure at least one trace point exists
        if not stack_trace:
            stack_trace.append(
                ProgramTrace(
                    trace_index=0,
                    path=Path("unknown"),
                    name=None,
                    line_idx=0,
                )
            )

        # Parse counterexample if spec provides one
        ce_spec = self.regex_spec.counterexample_spec
        if ce_spec:
            counterexample = self._parse_traces(
                issue_text,
                ce_spec,
                as_counterexample=True,
            )
            if counterexample:
                return VerifierIssue(
                    error_type=error_type,
                    message=message,
                    stack_trace=stack_trace,
                    counterexample=cast(
                        list[CounterexampleProgramTrace],
                        counterexample,
                    ),
                    severity=severity,
                )

        return Issue(
            error_type=error_type,
            message=message,
            stack_trace=stack_trace,
            severity=severity,
        )
