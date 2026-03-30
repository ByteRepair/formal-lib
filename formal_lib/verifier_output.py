# Author: Yiannis Charalambous

from abc import abstractmethod
from functools import cached_property
from pathlib import Path

from pydantic import Field, BaseModel

from formal_lib.program_trace import ProgramTrace
from formal_lib.issue import Issue, VerifierIssue


class VerifierOutput(BaseModel):
    """Class that represents the verifier output. All properties can be accessed
    directly in templates.

    This class provides both structured issue information (via the issues list)
    and convenient property access for single-error scenarios.
    """

    return_code: int
    """The return code of the verifier."""
    output: str
    """The output of the verifier."""
    issues: list[Issue] = Field(default_factory=list)
    """List of issues/errors found during verification."""
    duration: float | None = None
    """Execution time in seconds."""

    @property
    def issue_count(self) -> int:
        """Total number of issues found."""
        return len(self.issues)

    @property
    def successful(self) -> bool:
        """If the verification was successful."""
        return self.return_code == 0

    # Convenience methods

    @cached_property
    def primary_issue(self) -> Issue:
        """Returns the primary issue to address - the issue with highest severity.

        When multiple issues have the same severity level, returns the first one
        (which typically represents the root cause in execution order).
        """
        assert self.issues, "No issues found in verifier output"
        return max(self.issues, key=lambda issue: issue.severity_level)

    @property
    def error_line(self) -> int:
        """Returns the line number where the error occurred."""
        return self.issues[0].line_number

    @property
    def error_line_idx(self) -> int:
        """Returns the line index where the error occurred (0-based)."""
        return self.issues[0].line_index

    @property
    def error_message(self) -> str | None:
        """first error message from issues list."""
        return self.issues[0].message if self.issues else None

    @property
    def error_file(self) -> Path | None:
        """first error file path from issues list."""
        return self.issues[0].file_path if self.issues else None

    @property
    def error_type(self) -> str:
        """Returns a string of the type of error found by the verifier output."""
        return self.issues[0].error_type

    @property
    def stack_trace(self) -> list[ProgramTrace]:
        """Gets the stack trace that points to the error."""
        return self.issues[0].stack_trace

    def filter_traces(self, known_paths: set[Path]) -> "VerifierOutput":
        """Return a copy with traces filtered to only include known_paths.

        Issues whose stack traces are entirely filtered out are dropped. This
        method should be used to filter traces from library paths.
        """
        filtered_issues: list[Issue] = []

        for issue in self.issues:
            filtered_st = [t for t in issue.stack_trace if t.path in known_paths]
            if not filtered_st:
                continue

            if isinstance(issue, VerifierIssue):
                filtered_ce = [t for t in issue.counterexample if t.path in known_paths]
                new_issue: Issue = issue.model_copy(
                    update={
                        "stack_trace": filtered_st,
                        "counterexample": filtered_ce,
                    },
                )
            else:
                new_issue = issue.model_copy(update={"stack_trace": filtered_st})

            filtered_issues.append(new_issue)

        return self.model_copy(update={"issues": filtered_issues})
