# Author: Yiannis Charalambous

"""Regex-based parser for extracting structured issues from verifier output."""

import re
from typing import cast, get_args
from pathlib import Path

from formal_lib.program_trace import ProgramTrace, CounterexampleProgramTrace
from formal_lib.verifier_output import VerifierOutput
from formal_lib.issue import Issue, IssueSeverities, VerifierIssue
from formal_lib.regex import ANSI_ESCAPE_PATTERN
from formal_lib.specs.base import (
    AnnotatedPattern,
    CounterexampleRegexSpec,
    IssueRegexSpec,
    StackTraceRegexSpec,
)


class IssueSpecOutputParser:
    """Parses raw verifier output into structured issues using an IssueRegexSpec."""

    def __init__(self, regex_spec: IssueRegexSpec) -> None:
        self.regex_spec: IssueRegexSpec = regex_spec

    def parse_output(
        self, output: str, duration: float = 0.0
    ) -> VerifierOutput:
        # Strip ANSI escape codes in case the tool emits colored output.
        output = ANSI_ESCAPE_PATTERN.sub("", output)

        # Determine success from the spec's success pattern.
        spec = self.regex_spec
        if spec.success:
            matched = bool(re.search(spec.success, output, re.MULTILINE))
            successful = not matched if spec.negate_success else matched
        else:
            successful = True

        # Extract all issue blocks from the output
        issue_blocks: list[str] = []
        for match in re.finditer(spec.block, output, re.DOTALL | re.MULTILINE):
            issue_blocks.append(match.group(0))

        # Parse each issue block to extract individual issues
        issues: list[Issue] = [self._parse_issue(block) for block in issue_blocks]

        # Collect hints from annotated blocks that failed to match.
        hints: list[str] = []
        if not successful and not issues:
            hint = self._get_hint(spec.block)
            if hint:
                hints.append(hint)

        return VerifierOutput(
            successful=successful,
            issues=issues,
            output=output,
            duration=duration,
            hints=hints,
        )

    @staticmethod
    def _get_hint(pattern: str) -> str:
        return pattern.hint if isinstance(pattern, AnnotatedPattern) else ""

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
            name = name_match.group(1) if name_match and name_match.lastindex else None
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
        if severity_str not in get_args(IssueSeverities):
            severity_str = "error"
        # Type cast after validation
        severity: IssueSeverities = cast(IssueSeverities, severity_str)

        # Extract stack trace
        st_spec = self.regex_spec.stack_trace_spec
        stack_trace: list[ProgramTrace] = self._parse_traces(issue_text, st_spec)
        stack_trace_hint = self._get_hint(st_spec.block) if not stack_trace else ""

        # Parse counterexample if spec provides one
        ce_spec = self.regex_spec.counterexample_spec
        if ce_spec:
            counterexample = self._parse_traces(
                issue_text,
                ce_spec,
                as_counterexample=True,
            )
            counterexample_hint = (
                self._get_hint(ce_spec.block) if not counterexample else ""
            )
            return VerifierIssue(
                error_type=error_type,
                message=message,
                stack_trace=stack_trace,
                stack_trace_hint=stack_trace_hint,
                counterexample=cast(
                    list[CounterexampleProgramTrace],
                    counterexample,
                ),
                counterexample_hint=counterexample_hint,
                severity=severity,
            )

        return Issue(
            error_type=error_type,
            message=message,
            stack_trace=stack_trace,
            stack_trace_hint=stack_trace_hint,
            severity=severity,
        )
