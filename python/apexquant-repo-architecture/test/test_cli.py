from __future__ import annotations

from pathlib import Path

from apexquant_repo_architecture.cli import main
from test_scanner import create_minimal_repo


def test_cli_returns_zero_for_valid_repository(tmp_path: Path) -> None:
    create_minimal_repo(tmp_path)

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--json",
        ]
    )

    assert exit_code == 0


def test_cli_returns_one_for_invalid_repository(tmp_path: Path) -> None:
    create_minimal_repo(tmp_path)

    (tmp_path / "Makefile").unlink()

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--json",
        ]
    )

    assert exit_code == 1