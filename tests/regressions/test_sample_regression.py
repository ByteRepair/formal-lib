# Author: Yiannis Charalambous

"""Data-driven regression tests for verifier spec parsing.

Drop a .log and .json pair into tests/regressions/samples/<backend>/ and the
test runner will automatically pick it up. The .json file should contain the
expected JSON output from `pf --backend <backend> --format json-compact`, minus
the `output` field (which is just the raw log content).

A directory component whose name matches the version-range grammar
(``v6.7.0-v6.10.0``, ``v6.7.0-``, ``-v6.10.0``, or exact ``v6.7.1``) constrains
the samples beneath it: they only run against the backend's specs whose
supported versions overlap that range. Samples outside a version directory run
against every spec of their backend.
"""

import json
from pathlib import Path

import pytest

from formal_lib.issue_parser import IssueSpecOutputParser
from formal_lib.specs import SPECS
from formal_lib.specs.base import IssueRegexSpec
from formal_lib.version import VERSION_RANGE_PATTERN, VersionRange, as_range

SAMPLES_DIR = Path(__file__).parent / "samples"


ORPHANED: list[str] = []
"""Version-constrained samples whose range overlaps no spec of their backend —
silently dropping them would shrink the suite, so a test asserts this is empty."""


def discover_samples() -> list[tuple[str, IssueRegexSpec, Path, Path]]:
    """Discover .log/.json pairs and pair each with the specs it applies to."""
    cases = []
    for backend_dir in sorted(SAMPLES_DIR.iterdir()):
        specs = SPECS.get(backend_dir.name)
        if not backend_dir.is_dir() or not specs:
            continue
        for log_file in sorted(backend_dir.glob("**/*.log")):
            json_file = log_file.with_suffix(".json")
            if not json_file.exists():
                continue
            relative = log_file.relative_to(backend_dir)
            constraint = next(
                (
                    VersionRange.parse(part)
                    for part in relative.parts[:-1]
                    if VERSION_RANGE_PATTERN.fullmatch(part)
                ),
                None,
            )
            matched = [
                spec
                for spec in specs
                if constraint is None
                or any(as_range(v).overlaps(constraint) for v in spec.versions)
            ]
            if not matched:
                ORPHANED.append(f"{backend_dir.name}/{relative}")
                continue
            for spec in matched:
                sample_id = f"{backend_dir.name}/{relative.with_suffix('')}"
                if len(matched) > 1:
                    versions = ",".join(str(v) for v in spec.versions)
                    sample_id += f"@{versions}"
                cases.append((sample_id, spec, log_file, json_file))
    return cases


SAMPLES = discover_samples()


@pytest.mark.regression
def test_no_orphaned_samples() -> None:
    """Every version-constrained sample overlaps at least one spec's versions."""
    assert not ORPHANED


@pytest.mark.regression
@pytest.mark.parametrize(
    "spec, log_file, json_file",
    [case[1:] for case in SAMPLES],
    ids=[case[0] for case in SAMPLES],
)
def test_sample_output_matches_expected(
    spec: IssueRegexSpec, log_file: Path, json_file: Path
) -> None:
    log_content = log_file.read_text()
    expected = json.loads(json_file.read_text())

    result = IssueSpecOutputParser(spec).parse_output(log_content)

    actual = result.model_dump(mode="json")
    actual.pop("output", None)

    assert actual == expected
