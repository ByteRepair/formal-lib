# Author: Yiannis Charalambous

"""Regex-based parser for extracting structured issues from verifier output."""

import re
from typing import cast, get_args
from pathlib import Path

from formal_lib.program_trace import ProgramTrace, CounterexampleProgramTrace
from formal_lib.verifier_output import VerifierOutput
from formal_lib.issue import ErrorLocation, Issue, IssueSeverities, VerifierIssue
from formal_lib.regex import ANSI_ESCAPE_PATTERN
from formal_lib.specs.base import (
    AnnotatedPattern,
    CounterexampleRegexSpec,
    DeepestFirstPattern,
    ErrorLocationRegexSpec,
    FormattedPattern,
    IssueRegexSpec,
    MultiPattern,
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
        spec = self.regex_spec

        # Extract issue blocks, then parse each into an issue. The verdict's
        # data-driven baseline reads issue severities, so issues are parsed first.
        issue_blocks: list[str] = [
            match.group(0)
            for match in re.finditer(spec.block, output, re.DOTALL | re.MULTILINE)
        ]
        issues: list[Issue] = [self._parse_issue(block) for block in issue_blocks]

        successful = self._is_successful(output, issues)

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

    def _is_successful(self, output: str, issues: list[Issue]) -> bool:
        """Determine the verdict from a data-driven baseline gated by the spec's
        optional ``success`` / ``failure`` patterns.

        The run passed iff there is no error-severity issue AND — when the spec
        provides them — the positive ``success`` pattern matched and the ``failure``
        pattern did not. Warning/info issues never flip the verdict. The three
        checks are independent gates, so a miss in one (a failure whose pattern
        didn't match, or one the issue extractor dropped) is still caught by
        another; only a simultaneous miss reports a false success.
        """
        spec = self.regex_spec
        if any(issue.severity == "error" for issue in issues):
            return False
        if spec.success is not None and not re.search(
            spec.success, output, re.MULTILINE
        ):
            return False
        if spec.failure is not None and re.search(spec.failure, output, re.MULTILINE):
            return False
        return True

    @staticmethod
    def _get_hint(pattern: str) -> str:
        return pattern.hint if isinstance(pattern, AnnotatedPattern) else ""

    @staticmethod
    def _apply_format(pattern: str | None, value: str) -> str:
        return pattern.formatter(value) if isinstance(pattern, FormattedPattern) else value

    @staticmethod
    def _search_field(
        pattern: str, text: str
    ) -> tuple[re.Match[str] | None, str | None]:
        """Try each alternative in a ``MultiPattern`` until one matches; for a
        plain str pattern, behave like a single ``re.search``.

        Returns ``(None, None)`` when nothing matched; otherwise the match
        and the specific alternative that produced it (so per-branch
        ``FormattedPattern.formatter`` dispatch works inside a MultiPattern).
        """
        candidates: tuple[str, ...] = (
            pattern.patterns if isinstance(pattern, MultiPattern) else (pattern,)
        )
        for p in candidates:
            m = re.search(p, text, re.MULTILINE)
            if m is not None:
                return m, p
        return None, None

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

        # Some verifiers (ESBMC, CBMC, GDB-style) print frames deepest-first.
        # The deepest_first wrapper on trace_entry signals "reverse the
        # captured list" so consumers always see stack_trace[-1] as the
        # failure frame regardless of source-format direction. Re-index
        # after reversal so trace_index reflects post-reverse position.
        if isinstance(spec.trace_entry, DeepestFirstPattern):
            traces.reverse()
            for new_index, trace in enumerate(traces):
                trace.trace_index = new_index

        return traces

    @staticmethod
    def _parse_error_location(
        text: str, spec: ErrorLocationRegexSpec
    ) -> ErrorLocation | None:
        """Apply an ErrorLocationRegexSpec; return None when no match.

        Scopes path/line/column extraction to ``spec.block`` when the
        block regex is non-empty, else searches the whole issue text.
        Both ``path`` and ``line_index`` must capture for an
        ``ErrorLocation`` to be produced — a half-match returns None
        and the caller falls back to the stack trace.
        """
        scope = text
        if spec.block:
            block_match = re.search(spec.block, text, re.MULTILINE)
            if not block_match:
                return None
            scope = block_match.group(0)

        path_match = re.search(spec.path, scope) if spec.path else None
        line_match = re.search(spec.line_index, scope) if spec.line_index else None
        if not (path_match and line_match):
            return None

        column_idx: int | None = None
        if spec.column_index:
            col_match = re.search(spec.column_index, scope)
            if col_match:
                column_idx = int(col_match.group(1)) - 1

        return ErrorLocation(
            path=Path(path_match.group(1)),
            line_idx=int(line_match.group(1)) - 1,
            column_idx=column_idx,
        )

    def _parse_issue(self, issue_text: str) -> Issue:
        """Function that parses a single issue and returns it."""

        # Extract error type. The formatter is dispatched on the *matched*
        # alternative so MultiPattern branches can each carry their own
        # format_match (or none). _apply_format is a no-op when nothing matched.
        error_type_match, matched_et_pattern = self._search_field(
            self.regex_spec.error_type, issue_text
        )
        error_type = error_type_match.group(1) if error_type_match else "Unknown"
        error_type = self._apply_format(matched_et_pattern, error_type)

        # Extract message — same matched-pattern dispatch as error_type.
        message_match, matched_msg_pattern = self._search_field(
            self.regex_spec.message, issue_text
        )
        message = message_match.group(1) if message_match else ""
        message = self._apply_format(matched_msg_pattern, message)
        message = re.sub(r"\s*\n\s*", " ", message)

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

        # Extract explicit error-location header when the spec defines one.
        # When None on the spec or no match in the text, error_location stays
        # None and Issue.file_path falls back to stack_trace[-1].
        el_spec = self.regex_spec.error_location
        error_location: ErrorLocation | None = (
            self._parse_error_location(issue_text, el_spec) if el_spec else None
        )

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
                error_location=error_location,
            )

        return Issue(
            error_type=error_type,
            message=message,
            stack_trace=stack_trace,
            stack_trace_hint=stack_trace_hint,
            severity=severity,
            error_location=error_location,
        )
