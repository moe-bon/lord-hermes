import pytest

from apexquant_service_versioning.semver import (
    SemVer,
    SemVerError,
    highest_compatible,
    is_backward_compatible,
    parse_version,
)


def test_parse_valid_versions() -> None:
    assert parse_version("1.2.3") == SemVer(1, 2, 3)
    assert parse_version("0.1.0") == SemVer(0, 1, 0)
    assert parse_version("1.0.0-rc.1") == SemVer(1, 0, 0, "rc.1")
    assert parse_version("1.0.0+build.123") == SemVer(1, 0, 0, None, "build.123")


def test_parse_invalid_versions() -> None:
    with pytest.raises(SemVerError):
        parse_version("1.2")

    with pytest.raises(SemVerError):
        parse_version("v1.2.3")

    with pytest.raises(SemVerError):
        parse_version("01.2.3")


def test_semver_ordering() -> None:
    assert parse_version("1.2.3") < parse_version("1.2.4")
    assert parse_version("1.2.3") < parse_version("1.3.0")
    assert parse_version("1.0.0-rc.1") < parse_version("1.0.0")
    assert parse_version("1.0.0-alpha") < parse_version("1.0.0-beta")


def test_backward_compatibility_major_versions() -> None:
    assert is_backward_compatible("1.4.0", "1.2.0") is True
    assert is_backward_compatible("2.0.0", "1.2.0") is False
    assert is_backward_compatible("1.1.0", "1.2.0") is False


def test_backward_compatibility_zero_major_versions() -> None:
    assert is_backward_compatible("0.2.1", "0.2.0") is True
    assert is_backward_compatible("0.3.0", "0.2.0") is False


def test_highest_compatible_selection() -> None:
    candidates = ["1.2.0", "1.3.5", "1.4.2", "2.0.0"]

    assert highest_compatible(candidates, "1.2.0") == "1.4.2"
    assert highest_compatible(candidates, "2.0.0") == "2.0.0"
    assert highest_compatible(candidates, "3.0.0") is None