from __future__ import annotations

import re
from dataclasses import dataclass

SEMVER_PATTERN = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


class SemVerError(ValueError):
    pass


@dataclass(frozen=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: str | None = None
    build: str | None = None

    @classmethod
    def parse(cls, value: str) -> SemVer:
        match = SEMVER_PATTERN.match(value.strip())

        if match is None:
            raise SemVerError(f"invalid semantic version: {value}")

        return cls(
            major=int(match.group("major")),
            minor=int(match.group("minor")),
            patch=int(match.group("patch")),
            prerelease=match.group("prerelease"),
            build=match.group("build"),
        )

    @property
    def is_stable(self) -> bool:
        return self.prerelease is None

    def numeric_tuple(self) -> tuple[int, int, int]:
        return self.major, self.minor, self.patch

    def _prerelease_identifiers(self) -> list[str | int]:
        if self.prerelease is None:
            return []

        identifiers: list[str | int] = []

        for identifier in self.prerelease.split("."):
            if identifier.isdigit():
                identifiers.append(int(identifier))
            else:
                identifiers.append(identifier)

        return identifiers

    def compare(self, other: SemVer) -> int:
        if self.numeric_tuple() != other.numeric_tuple():
            return -1 if self.numeric_tuple() < other.numeric_tuple() else 1

        if self.prerelease is None and other.prerelease is None:
            return 0

        if self.prerelease is None and other.prerelease is not None:
            return 1

        if self.prerelease is not None and other.prerelease is None:
            return -1

        left = self._prerelease_identifiers()
        right = other._prerelease_identifiers()

        for left_identifier, right_identifier in zip(left, right):
            left_is_int = isinstance(left_identifier, int)
            right_is_int = isinstance(right_identifier, int)

            if left_is_int and right_is_int:
                if left_identifier != right_identifier:
                    return -1 if left_identifier < right_identifier else 1
            elif left_is_int and not right_is_int:
                return -1
            elif not left_is_int and right_is_int:
                return 1
            else:
                if left_identifier != right_identifier:
                    return -1 if str(left_identifier) < str(right_identifier) else 1

        if len(left) == len(right):
            return 0

        return -1 if len(left) < len(right) else 1

    def __lt__(self, other: SemVer) -> bool:
        return self.compare(other) < 0

    def __le__(self, other: SemVer) -> bool:
        return self.compare(other) <= 0

    def __gt__(self, other: SemVer) -> bool:
        return self.compare(other) > 0

    def __ge__(self, other: SemVer) -> bool:
        return self.compare(other) >= 0

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented

        return self.compare(other) == 0


def parse_version(value: str) -> SemVer:
    return SemVer.parse(value)


def is_backward_compatible(candidate: str, minimum: str) -> bool:
    candidate_version = SemVer.parse(candidate)
    minimum_version = SemVer.parse(minimum)

    if not candidate_version.is_stable:
        return False

    if candidate_version.major == 0 or minimum_version.major == 0:
        return (
            candidate_version.major == minimum_version.major
            and candidate_version.minor == minimum_version.minor
            and candidate_version >= minimum_version
        )

    return (
        candidate_version.major == minimum_version.major
        and candidate_version >= minimum_version
    )


def highest_compatible(candidates: list[str], minimum: str) -> str | None:
    compatible = [
        candidate
        for candidate in candidates
        if is_backward_compatible(candidate, minimum)
    ]

    if not compatible:
        return None

    parsed = sorted(
        compatible,
        key=lambda value: SemVer.parse(value),
        reverse=True,
    )

    return parsed[0]