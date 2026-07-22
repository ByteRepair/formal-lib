# Author: Yiannis Charalambous

"""Contains specs for different oracles."""

import re

from .base import (
    AnnotatedPattern,
    CachePropertiesFn,
    CounterexampleRegexSpec,
    FormattedPattern,
    IssueRegexSpec,
    StackTraceRegexSpec,
    format_match,
    missing_hint,
)
from .cbmc import cbmc_spec
from .clang import clang_spec
from .esbmc import esbmc_spec
from .kani import kani_spec
from .pytest import pytest_spec
from formal_lib.version import Version, VersionRange

SPECS: dict[str, list[IssueRegexSpec]] = {
    "esbmc": [esbmc_spec],
    # kani must precede cbmc: Kani's `--output-format old` output also carries a
    # `CBMC version` banner, so cbmc_spec.detect would otherwise claim it first.
    "kani": [kani_spec],
    "cbmc": [cbmc_spec],
    "clang": [clang_spec],
    "pytest": [pytest_spec],
}
"""Specs that the frontend currently supports, grouped by backend name. A backend
holds one spec per supported version range (list newest versions first); ranges
within a backend must not overlap (checked by ``hatch run check-specs``)."""


def detect_spec(output: str) -> IssueRegexSpec:
    """Auto-detect which spec matches the output using each spec's detect pattern."""
    for specs in SPECS.values():
        for spec in specs:
            if spec.detect and re.search(spec.detect, output, re.MULTILINE):
                return spec
    names = ", ".join(SPECS)
    raise ValueError(f"could not detect backend from output (known: {names})")


def resolve_spec(backend: str, output: str) -> IssueRegexSpec:
    """Pick the spec for a backend name. With several versioned specs, the first
    whose ``detect`` pattern matches the output wins; when none match, fall back
    to the first registered (the newest) spec."""
    specs = SPECS[backend]
    for spec in specs:
        if spec.detect and re.search(spec.detect, output, re.MULTILINE):
            return spec
    return specs[0]


__all__ = [
    "AnnotatedPattern",
    "CachePropertiesFn",
    "CounterexampleRegexSpec",
    "FormattedPattern",
    "IssueRegexSpec",
    "SPECS",
    "StackTraceRegexSpec",
    "Version",
    "VersionRange",
    "cbmc_spec",
    "clang_spec",
    "detect_spec",
    "esbmc_spec",
    "format_match",
    "kani_spec",
    "missing_hint",
    "pytest_spec",
    "resolve_spec",
]
