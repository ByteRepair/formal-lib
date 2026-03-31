# Author: Yiannis Charalambous

"""Data-driven regression tests for verifier spec parsing.

Drop a .log and .json pair into tests/regressions/samples/<spec>/ and the test
runner will automatically pick it up. The .json file should contain the expected
JSON output from `formal-lib --<spec> --format json-compact`, minus the `output`
field (which is just the raw log content).
"""

import json
import subprocess
from pathlib import Path

import pytest

SAMPLES_DIR = Path(__file__).parent / "samples"
KNOWN_SPECS = {"esbmc", "clang", "pytest"}


def discover_samples() -> list[tuple[str, Path, Path]]:
    """Discover all .log/.json pairs under samples/<spec>/."""
    pairs = []
    for spec_dir in sorted(SAMPLES_DIR.iterdir()):
        if not spec_dir.is_dir() or spec_dir.name not in KNOWN_SPECS:
            continue
        spec = spec_dir.name
        for log_file in sorted(spec_dir.glob("**/*.log")):
            json_file = log_file.with_suffix(".json")
            if json_file.exists():
                pairs.append((spec, log_file, json_file))
    return pairs


SAMPLES = discover_samples()
SAMPLE_IDS = [f"{spec}/{log.stem}" for spec, log, _ in SAMPLES]


@pytest.mark.regression
@pytest.mark.parametrize("spec, log_file, json_file", SAMPLES, ids=SAMPLE_IDS)
def test_sample_output_matches_expected(
    spec: str, log_file: Path, json_file: Path
) -> None:
    log_content = log_file.read_text()
    expected = json.loads(json_file.read_text())

    result = subprocess.run(
        ["formal-lib", "--backend", spec, "--format", "json-compact"],
        input=log_content,
        capture_output=True,
        text=True,
    )

    actual = json.loads(result.stdout)
    actual.pop("output", None)

    assert actual == expected
