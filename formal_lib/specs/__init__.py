# Author: Yiannis Charalambous

"""Contains specs for different oracles."""

import re

from .base import (
    CachePropertiesFn,
    CounterexampleRegexSpec,
    IssueRegexSpec,
    StackTraceRegexSpec,
)
from .cbmc import cbmc_spec
from .clang import clang_spec
from .esbmc import esbmc_spec
from .pytest import pytest_spec

SPECS: dict[str, IssueRegexSpec] = {
    "esbmc": esbmc_spec,
    "cbmc": cbmc_spec,
    "clang": clang_spec,
    "pytest": pytest_spec,
}
"""Specs that the frontend currently supports."""


def detect_spec(output: str) -> IssueRegexSpec:
    """Auto-detect which spec matches the output using each spec's detect pattern."""
    for _, spec in SPECS.items():
        if spec.detect and re.search(spec.detect, output, re.MULTILINE):
            return spec
    names = ", ".join(SPECS)
    raise ValueError(f"could not detect backend from output (known: {names})")


__all__ = [
    "CachePropertiesFn",
    "CounterexampleRegexSpec",
    "IssueRegexSpec",
    "SPECS",
    "StackTraceRegexSpec",
    "cbmc_spec",
    "clang_spec",
    "detect_spec",
    "esbmc_spec",
    "pytest_spec",
]
