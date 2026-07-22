# Author: Yiannis Charalambous

"""Version datatypes for declaring which verifier versions a spec supports.

A spec's ``versions`` list holds exact :class:`Version` entries and inclusive
:class:`VersionRange` entries. A range with ``lower=None`` extends back to the
earliest version, ``upper=None`` forward to the latest.

Regression-sample category directories use the same grammar, matched by
``VERSION_RANGE_PATTERN``: ``v6.7.0-v6.10.0`` (bounded), ``v6.7.0-`` (no upper
bound), ``-v6.10.0`` (no lower bound), or ``v6.7.1`` (exact version).
"""

import re
from dataclasses import dataclass

_VERSION = r"v\d+(?:\.\d+)*"
VERSION_RANGE_PATTERN = re.compile(rf"{_VERSION}-(?:{_VERSION})?|-{_VERSION}|{_VERSION}")
"""Grammar for a version-range category name; use with ``fullmatch``. A bare
``-`` (unbounded on both sides) is deliberately rejected — an unconstrained
category is expressed by not using a version directory at all."""


@dataclass(frozen=True, order=True)
class Version:
    """A dotted numeric version, compared numerically part by part.

    Trailing zero parts are normalized away so ``6.7.0 == 6.7``.
    """

    parts: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.parts:
            raise ValueError("version needs at least one part")
        parts = self.parts
        while len(parts) > 1 and parts[-1] == 0:
            parts = parts[:-1]
        object.__setattr__(self, "parts", parts)

    @classmethod
    def parse(cls, text: str) -> "Version":
        """Parse ``6.7.1`` or ``v6.7.1`` into a Version."""
        body = text.removeprefix("v")
        if not re.fullmatch(r"\d+(?:\.\d+)*", body):
            raise ValueError(f"invalid version: {text!r}")
        return cls(tuple(int(part) for part in body.split(".")))

    def __str__(self) -> str:
        return ".".join(str(part) for part in self.parts)


@dataclass(frozen=True)
class VersionRange:
    """An inclusive version range; a ``None`` bound means unbounded on that side.

    The default ``VersionRange()`` is unbounded on both sides — "all versions".
    """

    lower: Version | None = None
    upper: Version | None = None

    def __post_init__(self) -> None:
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError(f"range lower bound {self.lower} exceeds upper bound {self.upper}")

    @classmethod
    def parse(cls, text: str) -> "VersionRange":
        """Parse a category name matching ``VERSION_RANGE_PATTERN``.

        ``v6.7.0-v6.10.0`` | ``v6.7.0-`` | ``-v6.10.0`` | ``v6.7.1`` (exact).
        """
        if not VERSION_RANGE_PATTERN.fullmatch(text):
            raise ValueError(f"invalid version range: {text!r}")
        if "-" not in text:
            exact = Version.parse(text)
            return cls(exact, exact)
        lower_text, upper_text = text.split("-", 1)
        return cls(
            Version.parse(lower_text) if lower_text else None,
            Version.parse(upper_text) if upper_text else None,
        )

    def __contains__(self, version: Version) -> bool:
        return (self.lower is None or self.lower <= version) and (
            self.upper is None or version <= self.upper
        )

    def overlaps(self, other: "Version | VersionRange") -> bool:
        """Whether at least one version falls in both ranges (bounds inclusive)."""
        other = as_range(other)
        return (self.lower is None or other.upper is None or self.lower <= other.upper) and (
            other.lower is None or self.upper is None or other.lower <= self.upper
        )

    def __str__(self) -> str:
        if self.lower is not None and self.lower == self.upper:
            return f"v{self.lower}"
        lower = f"v{self.lower}" if self.lower is not None else ""
        upper = f"v{self.upper}" if self.upper is not None else ""
        return f"{lower}-{upper}"


def as_range(value: Version | VersionRange) -> VersionRange:
    """Normalize a supported-versions entry: an exact Version becomes ``[v, v]``."""
    return value if isinstance(value, VersionRange) else VersionRange(value, value)
