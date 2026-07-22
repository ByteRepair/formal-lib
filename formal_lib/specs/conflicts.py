# Author: Yiannis Charalambous

"""Spec version-conflict checker, run via ``hatch run check-specs``.

Within one backend, each version must be handled by at most one spec — two
specs whose supported versions overlap is a spec conflict, because backend
resolution could no longer tell which spec owns output from that version.

``check-specs -v`` additionally lists every spec and the versions it supports.
"""

import argparse
import sys
from itertools import combinations

from formal_lib.specs import SPECS
from formal_lib.specs.base import IssueRegexSpec
from formal_lib.version import Version, VersionRange, as_range


def _describe(versions: list[Version | VersionRange]) -> str:
    """Render a supported-versions list; the all-unbounded default reads "any version"."""
    return ", ".join(
        "any version" if v == VersionRange() else str(v) for v in versions
    )


def find_conflicts(specs: dict[str, list[IssueRegexSpec]] = SPECS) -> list[str]:
    """Return one message per pair of same-backend specs with overlapping versions."""
    conflicts: list[str] = []
    for backend, backend_specs in specs.items():
        for (i, first), (j, second) in combinations(enumerate(backend_specs), 2):
            if any(
                as_range(a).overlaps(b)
                for a in first.versions
                for b in second.versions
            ):
                conflicts.append(
                    f"{backend}: spec #{i} [{_describe(first.versions)}] overlaps "
                    f"spec #{j} [{_describe(second.versions)}]"
                )
    return conflicts


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="check-specs",
        description="Check that no two specs of one backend support the same "
        "verifier version.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="list every spec and the versions it supports",
    )
    args = parser.parse_args()

    if args.verbose:
        for backend, backend_specs in SPECS.items():
            print(f"{backend}:")
            for i, spec in enumerate(backend_specs):
                print(f"  spec #{i}: {_describe(spec.versions)}")

    conflicts = find_conflicts()
    for conflict in conflicts:
        print(f"spec conflict: {conflict}", file=sys.stderr)
    if conflicts:
        sys.exit(1)
    spec_count = sum(len(specs) for specs in SPECS.values())
    print(f"OK: no version overlap across {spec_count} specs in {len(SPECS)} backends")


if __name__ == "__main__":
    main()
