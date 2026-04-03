# Author: Yiannis Charalambous

"""Base dataclasses that define the regex specification contract for verifier backends."""

from collections.abc import Callable
from typing import Any, Protocol
from dataclasses import dataclass, field
from pathlib import Path


class AnnotatedPattern(str):
    """A regex pattern string annotated with a hint for when it fails to match."""

    hint: str

    def __new__(cls, pattern: str, hint: str) -> "AnnotatedPattern":
        instance = super().__new__(cls, pattern)
        instance.hint = hint
        return instance


class FormattedPattern(str):
    """A regex pattern string with a post-processing formatter for captured values."""

    formatter: Callable[[str], str]

    def __new__(cls, pattern: str, formatter: Callable[[str], str]) -> "FormattedPattern":
        instance = super().__new__(cls, pattern)
        instance.formatter = formatter
        return instance


class format_match:
    """Annotate a field pattern with a post-processing formatter.

    Usage in spec definitions::

        message=format_match(lambda v: v.replace("\\n", " "))(r"pattern")
    """

    def __init__(self, formatter: Callable[[str], str]) -> None:
        self.formatter = formatter

    def __call__(self, pattern: str) -> FormattedPattern:
        return FormattedPattern(pattern, self.formatter)


class missing_hint:
    """Annotate a block pattern with a hint shown when the block fails to match.

    Usage in spec definitions::

        block=missing_hint("Needs --trace")(r"Trace for [^\\n]+:\\n...")
    """

    def __init__(self, hint: str) -> None:
        self.hint = hint

    def __call__(self, pattern: str) -> AnnotatedPattern:
        return AnnotatedPattern(pattern, self.hint)


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
    detect: str = ""
    """Regex pattern to detect if output was produced by this verifier.
    Matched against the full output with MULTILINE. Empty means no auto-detection."""
    counterexample_spec: CounterexampleRegexSpec | None = None
    """Optional nested specification for parsing counterexample traces."""
    success: str = ""
    """Regex pattern for determining verification success from output text.
    Matched with re.MULTILINE against the full output."""
    negate_success: bool = False
    """When False, a match means success. When True, a match means failure
    (i.e. success is the absence of the pattern)."""
    cache_properties: CachePropertiesFn | None = field(default=None)
    """Optional function to compute cache properties from verify_source args.
    When None, default properties are used."""
