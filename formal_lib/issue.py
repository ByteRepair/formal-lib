# Author: Yiannis Charalambous


from typing import Literal
from pathlib import Path

from pydantic import Field, BaseModel

from formal_lib.program_trace import ProgramTrace, CounterexampleProgramTrace

IssueSeverities = Literal["error", "warning", "info"]


class ErrorLocation(BaseModel):
    """Explicit error-location header captured from the verifier's output.

    Some verifiers print a dedicated "this is where the failure is" line
    separate from any call stack (ESBMC's ``Violated property:``, clang's
    diagnostic header, etc.). When the spec captures one, the parsed
    ``ErrorLocation`` is the canonical violation site — preferred over
    the stack trace's last frame for ``file_path`` / ``line_index`` /
    ``line_number`` resolution.

    Distinct from ``ProgramTrace`` because the violation site is a
    location, not a call frame: it has no caller relationship, no symbol
    resolution, and exists once per issue, not once per visited frame.
    """

    path: Path = Field()
    """The source file the violation is reported in."""
    line_idx: int = Field()
    """The 0-based line index of the violation."""
    column_idx: int | None = Field(default=None)
    """Optional 0-based column index, when the verifier prints one."""


class Issue(BaseModel):
    """Generic issue/error representation.

    Location data is taken from ``error_location`` when the spec captured
    one (the verifier's explicit error-location header), falling back to
    ``stack_trace[-1]`` otherwise. ``stack_trace`` continues to describe
    the call chain leading to the failure.
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
    """Hint shown inline when stack_trace is empty (e.g. missing verifier flag)."""
    error_location: ErrorLocation | None = Field(default=None)
    """Explicit error-location header parsed from the verifier output, when
    the spec provides one. ``Issue`` location properties prefer this over
    the stack trace's last frame."""

    # Convenience properties.
    # Location-bearing properties read from ``error_location`` when the
    # spec captured one, else fall back to ``stack_trace[-1]``. Defined
    # via _loc to keep the five primitive accessors uniform — adding a
    # sixth means one line, not another if/else.

    def _loc(self, el_attr: str, frame_attr: str):
        """Return ``error_location.<el_attr>`` if set, else
        ``stack_trace[-1].<frame_attr>``. Raises ``IndexError`` if both
        are absent — callers that need a None-safe fallback should guard
        on ``stack_trace`` themselves."""
        if self.error_location is not None:
            return getattr(self.error_location, el_attr)
        return getattr(self.stack_trace[-1], frame_attr)

    @property
    def severity_level(self) -> int:
        match self.severity:
            case "info":
                return 0
            case "warning":
                return 1
            case "error":
                return 2

    @property
    def file_path(self) -> Path:
        return self._loc("path", "path")

    @property
    def line_index(self) -> int:
        return self._loc("line_idx", "line_idx")

    @property
    def line_number(self) -> int:
        return self.line_index + 1

    @property
    def column_index(self) -> int | None:
        # Stack-trace frames don't carry columns, so this is error_location-only.
        return self.error_location.column_idx if self.error_location else None

    @property
    def column_number(self) -> int | None:
        idx = self.column_index
        return idx + 1 if idx is not None else None

    @property
    def function_name(self) -> str | None:
        """Function name at the violation site.

        When ``error_location`` is set, prefer a stack frame whose path
        matches and whose ``name`` is non-None — this skips wrapper /
        instrumentation frames at the top of the trace (e.g. ESBMC's
        ``__ESBMC_contracts_original_*`` under --enforce-contracts, whose
        name doesn't resolve via the spec's name regex). Otherwise the
        innermost frame's name is the right answer.
        """
        if self.error_location is not None:
            for frame in reversed(self.stack_trace):
                if (
                    frame.path == self.error_location.path
                    and frame.name is not None
                ):
                    return frame.name
        if self.stack_trace:
            return self.stack_trace[-1].name
        return None

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
    """Hint shown inline when counterexample is empty (e.g. missing verifier flag)."""

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
