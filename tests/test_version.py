# Author: Yiannis Charalambous

"""Tests for the Version/VersionRange datatypes and the spec conflict checker."""

import pytest

from formal_lib.specs import SPECS
from formal_lib.specs.base import IssueRegexSpec, StackTraceRegexSpec
from formal_lib.specs.conflicts import find_conflicts
from formal_lib.version import VERSION_RANGE_PATTERN, Version, VersionRange, as_range


# --- Version ---

def test_version_parse() -> None:
    assert Version.parse("6.7.1") == Version((6, 7, 1))
    assert Version.parse("v6.7.1") == Version((6, 7, 1))
    assert Version.parse("8") == Version((8,))


def test_version_parse_rejects_garbage() -> None:
    for text in ("", "v", "6.", "6.x", "6-7"):
        with pytest.raises(ValueError):
            Version.parse(text)


def test_version_ordering_is_numeric() -> None:
    assert Version.parse("6.10") > Version.parse("6.7")
    assert Version.parse("6.7") < Version.parse("6.7.1")


def test_version_normalizes_trailing_zeros() -> None:
    assert Version.parse("6.7.0") == Version.parse("6.7")
    assert str(Version.parse("1.0.0")) == "1"


# --- VersionRange ---

def test_range_parse_bounded() -> None:
    r = VersionRange.parse("v6.7.0-v6.10.0")
    assert r.lower == Version.parse("6.7")
    assert r.upper == Version.parse("6.10")


def test_range_parse_unbounded_sides() -> None:
    assert VersionRange.parse("v6.7.0-").upper is None
    assert VersionRange.parse("-v6.10.0").lower is None


def test_range_parse_exact_version() -> None:
    r = VersionRange.parse("v6.7.1")
    assert r.lower == r.upper == Version.parse("6.7.1")


def test_range_parse_rejects_non_ranges() -> None:
    # Plain category names must never parse as version ranges.
    for text in ("contracts", "esbmc-cpp", "linux", "-", "v6.7-x"):
        assert not VERSION_RANGE_PATTERN.fullmatch(text)
        with pytest.raises(ValueError):
            VersionRange.parse(text)


def test_range_rejects_inverted_bounds() -> None:
    with pytest.raises(ValueError):
        VersionRange(Version.parse("2"), Version.parse("1"))


def test_range_contains_inclusive_bounds() -> None:
    r = VersionRange.parse("v6.7.0-v6.10.0")
    assert Version.parse("6.7.0") in r
    assert Version.parse("6.10.0") in r
    assert Version.parse("6.8.2") in r
    assert Version.parse("6.6.9") not in r
    assert Version.parse("6.10.1") not in r


def test_unbounded_range_contains_everything() -> None:
    assert Version.parse("0.0.1") in VersionRange()
    assert Version.parse("999") in VersionRange()


def test_overlaps() -> None:
    assert VersionRange.parse("v1-v3").overlaps(VersionRange.parse("v3-v5"))  # touching, inclusive
    assert not VersionRange.parse("v1-v3").overlaps(VersionRange.parse("v3.0.1-v5"))
    assert VersionRange.parse("v4-").overlaps(VersionRange())  # unbounded overlaps all
    assert VersionRange.parse("-v3").overlaps(Version.parse("2.5"))
    assert not VersionRange.parse("-v3").overlaps(Version.parse("3.1"))


def test_as_range() -> None:
    assert as_range(Version.parse("2")) == VersionRange.parse("v2")
    r = VersionRange.parse("v1-v2")
    assert as_range(r) is r


def test_range_str() -> None:
    assert str(VersionRange.parse("v1-v2")) == "v1-v2"
    assert str(VersionRange.parse("v6.7.1")) == "v6.7.1"
    assert str(VersionRange.parse("-v3")) == "-v3"
    assert str(VersionRange()) == "any version"


# --- spec conflict checker ---

_NO_TRACE = StackTraceRegexSpec(
    block=r"ZZZ_NOMATCH", trace_entry=r"ZZZ", trace_index=r"ZZZ",
    path=r"ZZZ", name=r"ZZZ", line_index=r"ZZZ",
)


def _spec(*versions: Version | VersionRange) -> IssueRegexSpec:
    spec = IssueRegexSpec(
        block=r"ZZZ",
        error_type=r"ZZZ",
        message=r"ZZZ",
        severity=r"ZZZ",
        stack_trace_spec=_NO_TRACE,
    )
    if versions:  # no args -> keep the default all-versions range
        spec.versions = list(versions)
    return spec


def test_spec_supports() -> None:
    spec = _spec(Version.parse("2"), VersionRange.parse("v5-v6"))
    assert spec.supports(Version.parse("2"))
    assert spec.supports(VersionRange.parse("v6-v9"))
    assert not spec.supports(VersionRange.parse("v3-v4.9"))


def test_disjoint_specs_do_not_conflict() -> None:
    specs = {
        "tool": [
            _spec(VersionRange.parse("v8-")),
            _spec(VersionRange.parse("-v7.99")),
        ]
    }
    assert find_conflicts(specs) == []


def test_overlapping_specs_conflict() -> None:
    specs = {
        "tool": [
            _spec(VersionRange.parse("v7-")),
            _spec(VersionRange.parse("-v7.5")),
        ]
    }
    conflicts = find_conflicts(specs)
    assert len(conflicts) == 1
    assert "tool" in conflicts[0]


def test_default_all_versions_specs_conflict() -> None:
    # Two specs left on the default unbounded range must be flagged.
    assert len(find_conflicts({"tool": [_spec(), _spec()]})) == 1


def test_same_versions_in_different_backends_do_not_conflict() -> None:
    specs = {
        "tool_a": [_spec(VersionRange.parse("v1-v2"))],
        "tool_b": [_spec(VersionRange.parse("v1-v2"))],
    }
    assert find_conflicts(specs) == []


def test_registered_specs_have_no_conflicts() -> None:
    assert find_conflicts(SPECS) == []
