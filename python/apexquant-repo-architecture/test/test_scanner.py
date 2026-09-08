from __future__ import annotations

from pathlib import Path

from apexquant_repo_architecture.scanner import (
    REQUIRED_DIRS,
    REQUIRED_FILES,
    scan_repo,
)


def create_minimal_repo(root: Path) -> None:
    for required in REQUIRED_DIRS:
        (root / required.path).mkdir(parents=True, exist_ok=True)

    for required in REQUIRED_FILES:
        file_path = root / required.path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if required.path == "Cargo.toml":
            file_path.write_text(
                """
[workspace]
resolver = "2"
members = [
    "crates/control/service-framework-core",
]
""".strip()
                + "\n",
                encoding="utf-8",
            )
        elif required.path == "pyproject.toml":
            file_path.write_text(
                """
[project]
name = "apexquant-ultra"
version = "0.1.0"
requires-python = ">=3.13"
""".strip()
                + "\n",
                encoding="utf-8",
            )
        elif required.path == "crates/control/service-framework-core/Cargo.toml":
            file_path.write_text(
                """
[package]
name = "service-framework-core"
version = "0.1.0"
edition = "2021"
""".strip()
                + "\n",
                encoding="utf-8",
            )
        elif required.path == "python/apexquant-service-framework/pyproject.toml":
            file_path.write_text(
                """
[project]
name = "apexquant-service-framework"
version = "0.1.0"
requires-python = ">=3.13"
""".strip()
                + "\n",
                encoding="utf-8",
            )
        elif required.path == "python/apexquant-repo-architecture/pyproject.toml":
            file_path.write_text(
                """
[project]
name = "apexquant-repo-architecture"
version = "0.1.0"
requires-python = ">=3.13"
""".strip()
                + "\n",
                encoding="utf-8",
            )
        else:
            file_path.write_text("", encoding="utf-8")

    crate_dir = root / "crates/control/service-framework-core"
    crate_dir.mkdir(parents=True, exist_ok=True)

    service_framework_src = root / "python/apexquant-service-framework/src"
    repo_architecture_src = root / "python/apexquant-repo-architecture/src"

    service_framework_src.mkdir(parents=True, exist_ok=True)
    repo_architecture_src.mkdir(parents=True, exist_ok=True)


def test_valid_repository_has_no_errors(tmp_path: Path) -> None:
    create_minimal_repo(tmp_path)

    report = scan_repo(tmp_path)

    assert report.ok
    assert report.errors_count == 0
    assert "crates/control/service-framework-core" in report.cargo_members
    assert "apexquant-service-framework" in report.python_packages
    assert "apexquant-repo-architecture" in report.python_packages


def test_missing_required_file_is_error(tmp_path: Path) -> None:
    create_minimal_repo(tmp_path)

    (tmp_path / "Makefile").unlink()

    report = scan_repo(tmp_path)

    assert not report.ok
    assert report.errors_count >= 1
    assert any(
        violation.code == "MISSING_FILE" and violation.path == "Makefile"
        for violation in report.violations
    )


def test_missing_workspace_member_manifest_is_error(tmp_path: Path) -> None:
    create_minimal_repo(tmp_path)

    crate_manifest = tmp_path / "crates/control/service-framework-core/Cargo.toml"
    crate_manifest.unlink()

    report = scan_repo(tmp_path)

    assert not report.ok
    assert any(
        violation.code == "MISSING_CARGO_MANIFEST"
        for violation in report.violations
    )


def test_python_package_missing_src_layout_is_error(tmp_path: Path) -> None:
    create_minimal_repo(tmp_path)

    src_dir = tmp_path / "python/apexquant-repo-architecture/src"

    for child in src_dir.iterdir():
        if child.is_file():
            child.unlink()

    src_dir.rmdir()

    report = scan_repo(tmp_path)

    assert not report.ok
    assert any(
        violation.code == "MISSING_SRC_LAYOUT"
        for violation in report.violations
    )


def test_unexpected_top_level_entry_is_warning(tmp_path: Path) -> None:
    create_minimal_repo(tmp_path)

    (tmp_path / "unexpected-directory").mkdir()

    report = scan_repo(tmp_path)

    assert report.ok
    assert report.warnings_count >= 1
    assert any(
        violation.code == "UNEXPECTED_TOP_LEVEL_ENTRY"
        for violation in report.violations
    )

    strict_report = scan_repo(tmp_path, strict_warnings=True)

    assert not strict_report.ok