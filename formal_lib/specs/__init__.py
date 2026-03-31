# Author: Yiannis Charalambous

"""Contains specs for different oracles."""

from .cbmc import cbmc_spec
from .clang import clang_spec
from .esbmc import esbmc_spec
from .pytest import pytest_spec

__all__ = [
    "cbmc_spec",
    "clang_spec",
    "esbmc_spec",
    "pytest_spec",
]
