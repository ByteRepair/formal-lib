# Author: Yiannis Charalambous


from typing import Literal
from pathlib import Path

from pydantic import Field, BaseModel

from formal_lib.program_trace import ProgramTrace, CounterexampleProgramTrace

IssueSeverities = Literal["error", "warning", "info"]


class Issue(BaseModel):
    """Generic issue/error representation.

    Uses stack_trace as the single source of truth for location information.
    All issues must have at least one trace point describing the error location.
    Simple errors have a single trace point, while complex errors have multiple
    trace points.
    """

    error_type: str = Field(description="Category/type of error.")
    """Category/type of error."""
    message: str = Field(description="Error description.")
    """Error description."""
    stack_trace: list[ProgramTrace] = Field(
        description="Stack trace as structured data.",
    )
    """Stack trace as structured data."""
    severity: IssueSeverities = Field(default="error", description="Severity level.")
    """Severity level."""
    stack_trace_hint: str = Field(default="", exclude=True)
    """Hint explaining why stack_trace may be empty (e.g. missing verifier flag)."""

    # Convenience properties
    # Note: All properties derive from the last trace point (stack_trace[-1]) as this
    # represents the point of failure in the stack trace. Earlier trace points show
    # the call chain leading to the error.

    @property
    def severity_level(self) -> int:
        """Returns the severity as an int."""
        match self.severity:
            case "info":
                return 0
            case "warning":
                return 1
            case "error":
                return 2

    @property
    def file_path(self) -> Path:
        """Path to file with issue (derived from last trace point)."""
        return self.stack_trace[-1].path

    @property
    def line_index(self) -> int:
        """Line index where the error occurred (derived from last trace point, 0-based)"""
        return self.stack_trace[-1].line_idx

    @property
    def line_number(self) -> int:
        """Line number where error occurred (derived from last trace point, 1-based)."""
        return self.stack_trace[-1].line_idx + 1

    @property
    def function_name(self) -> str | None:
        """Function name where error occurred (derived from last trace point)."""
        return self.stack_trace[-1].name

    @property
    def stack_trace_formatted(self) -> str:
        """Returns a formatted string representation of the stack trace.

        Format: Each trace on a new line showing function name and location.
        Example:
            at main in file.c:15
            at helper in file.c:42
        """
        if not self.stack_trace:
            hint = f" ({self.stack_trace_hint})" if self.stack_trace_hint else ""
            return f"Not available{hint}"
        lines = []
        for trace in self.stack_trace:
            func_name = trace.name if trace.name else "<unknown>"
            line_num = trace.line_idx + 1  # Convert to 1-based
            lines.append(f"\tat {func_name} in {trace.path}:{line_num}")
        return "\n".join(lines)


class VerifierIssue(Issue):
    """Verifier-specific issue with additional verification data.

    This class extends Issue to support verifiers like ESBMC that can provide
    counterexamples in addition to stack traces:

    - stack_trace: Traditional function call stack showing the path to the error
    - counterexample: Program state trace showing variable values and execution
      states that lead to the bug. This is specific to model checkers and formal
      verification tools like ESBMC.

    Note: Not all verifiers support counterexamples (e.g., pytest only provides
    stack traces). Use this class only when counterexample data is available.
    """

    counterexample: list[CounterexampleProgramTrace] = Field(
        description="Counterexample demonstrating bug."
    )
    """Counterexample demonstrating bug."""
    counterexample_hint: str = Field(default="", exclude=True)
    """Hint explaining why counterexample may be empty (e.g. missing verifier flag)."""

    @property
    def counterexample_formatted(self) -> str:
        """Returns a formatted string representation of the counterexample trace.

        Format: Each trace on a new line showing function name, location, and
        assignment (if available).
        Example:
            State 0: at main in file.c:15
              dist = { 0, 0, 0, 0, 0 }
            State 1: at helper in file.c:42
              dist[0] = 2147483647 (01111111 11111111 11111111 11111111)
        """
        if not self.counterexample:
            hint = f" ({self.counterexample_hint})" if self.counterexample_hint else ""
            return f"Not available{hint}"
        lines = []
        for trace in self.counterexample:
            func_name = trace.name if trace.name else "<unknown>"
            line_num = trace.line_idx + 1  # Convert to 1-based
            lines.append(
                f"\tState {trace.trace_index}: at {func_name} in {trace.path}:{line_num}"
            )
            # Add assignment information if available
            if trace.assignment:
                lines.append("\t\t" + trace.assignment.replace("\n", "\n\t\t"))
        return "\n".join(lines)
