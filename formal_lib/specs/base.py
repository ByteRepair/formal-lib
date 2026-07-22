# Author: Yiannis Charalambous

"""Base dataclasses that define the regex specification contract for verifier backends."""

from collections.abc import Callable
from typing import Any, Protocol
from dataclasses import dataclass, field
from pathlib import Path

from formal_lib.version import Version, VersionRange, as_range


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


class DeepestFirstPattern(str):
    """A trace_entry pattern whose match order lists deepest frames first.

    The parser detects this subclass and reverses the captured trace list so
    consumers can rely on the convention "stack_trace[-1] is the failure
    frame" regardless of how the verifier prints frames in its raw output.
    """


class MultiPattern(str):
    """A field pattern that delegates to one of N regexes, tried in order.

    The str value is the primary so a bare ``re.search(spec.field, text)``
    hits the primary — preserves back-compat for any consumer that doesn't
    know about MultiPattern. The parser dispatches on the subclass via
    ``isinstance`` and iterates ``patterns`` (primary first, then fallbacks).
    """

    patterns: tuple[str, ...]

    def __new__(cls, primary: str, fallbacks: tuple[str, ...]) -> "MultiPattern":
        instance = super().__new__(cls, primary)
        instance.patterns = (primary,) + fallbacks
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


def try_patterns(primary: str, *fallbacks: str) -> MultiPattern:
    """Wrap a primary pattern with one or more fallbacks tried in order.

    Usage in spec definitions::

        error_type=try_patterns(
            r"Violated property:\\n\\s+file[^\\n]*\\n\\s+([^\\n]+?)\\s*$",
            r"Stack trace:\\n(?:\\s+c:@\\S*[^\\n]*\\n)*\\s+(\\S+)",
        ),

    Each pattern is matched independently — no negative lookaheads needed
    between branches. Patterns may individually be wrapped with
    ``format_match`` to attach a per-pattern formatter; the parser dispatches
    on whichever branch matched.

    Pattern priority should reflect production reality: the shape that fires
    most often in real usage goes first.
    """
    return MultiPattern(primary, fallbacks)


class deepest_first:
    """Annotate a trace_entry pattern: parsed traces will be reversed.

    Use when the verifier prints stack frames deepest-first (ESBMC, CBMC,
    GDB-style traces). pytest / Python tracebacks print outermost-first
    and don't need this. Without the annotation, the parser stores frames
    in source order; with it, the parser reverses the list once after
    building it so ``stack_trace[-1]`` is always the failure frame.

    Usage in spec definitions::

        trace_entry=deepest_first()(r"^[^\\n]*\\bfile\\s+\\S+\\s+line\\s+\\d+[^\\n]*"),
    """

    def __call__(self, pattern: str) -> DeepestFirstPattern:
        return DeepestFirstPattern(pattern)


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
class ErrorLocationRegexSpec:
    """Regex specification for the verifier's explicit error-location header.

    Some verifiers print a dedicated "this is where the failure is" line
    that's separate from any call stack — ESBMC's ``Violated property:``
    block, clang's ``<file>:<line>:<col>: error:`` diagnostic header, etc.
    When a spec fills this in, ``Issue.file_path`` / ``line_index`` /
    ``line_number`` prefer the captured location over the stack trace's
    last frame. This matters for verifiers (like ESBMC under
    ``--enforce-contract``) where contract instrumentation can pin the
    visible stack frames to a wrapper line that isn't where execution
    actually failed.

    Optional. When the field is None on an ``IssueRegexSpec``, the
    parser doesn't run the regex and ``Issue.error_location`` stays
    None — consumers fall back to the stack-trace-derived location.
    """

    block: str = ""
    """Optional scoping regex; ``""`` (the default) means "scan the whole
    issue text." This differs from :class:`StackTraceRegexSpec.block`, which
    is mandatory and always names a sub-block — error locations are usually
    a single header line and don't need a containing scope, but specs can
    opt into one (e.g. to refuse matches outside a ``Violated property:``
    region) by setting this."""
    path: str = ""
    """Regex with one capture group for the file path."""
    line_index: str = ""
    """Regex with one capture group for the 1-based line number."""
    column_index: str = ""
    """Optional regex with one capture group for the 1-based column.
    Empty string means no column extracted."""


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
    versions: list[Version | VersionRange] = field(default_factory=lambda: [VersionRange()])
    """Verifier versions this spec's patterns are written for: exact ``Version``
    entries and/or inclusive ``VersionRange`` entries (a ``None`` bound means
    unbounded on that side). The default single unbounded range means "all
    versions". When a verifier changes its output format, register a second spec
    under the same backend name in ``SPECS`` and constrain both specs' versions —
    within one backend no two specs may support the same version (checked by
    ``hatch run check-specs``)."""
    counterexample_spec: CounterexampleRegexSpec | None = None
    """Optional nested specification for parsing counterexample traces."""
    error_location: ErrorLocationRegexSpec | None = None
    """Optional nested specification for the verifier's explicit error-location
    header (e.g. ESBMC's ``Violated property:`` block, clang's diagnostic
    header). When set, ``Issue`` properties prefer this location over the
    stack trace's last frame."""
    success: str | None = None
    """Regex whose match confirms the run PASSED — a positive verdict line such as
    ESBMC/CBMC's ``VERIFICATION SUCCESSFUL``. Fail-closed: when set and it does not
    match, the run is reported as failed. ``None`` skips this gate. re.MULTILINE."""
    failure: str | None = None
    """Regex whose match forces the verdict to FAILED. Use it for verifiers with no
    positive success signal, or whose failures don't always surface as issues (e.g.
    Kani run without ``--trace``) so the pattern gates those cases. ``None`` skips it.
    re.MULTILINE.

    ``success`` and ``failure`` layer on the data-driven baseline; see
    :meth:`IssueSpecOutputParser._is_successful` for how the three combine."""
    cache_properties: CachePropertiesFn | None = field(default=None)
    """Optional function to compute cache properties from verify_source args.
    When None, default properties are used."""

    def supports(self, target: Version | VersionRange) -> bool:
        """Whether any entry in ``versions`` overlaps ``target``.

        The single interpretation of the ``versions`` field — shared by the
        conflict checker and the regression suite's version-directory scoping
        so the two can never disagree about which specs a version maps to."""
        return any(as_range(v).overlaps(target) for v in self.versions)
