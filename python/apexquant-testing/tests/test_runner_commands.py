import sys
from pathlib import Path

from apexquant_testing.runner import build_cargo_command, build_pytest_command


def test_build_pytest_command() -> None:
    command = build_pytest_command(
        package_dir=Path("python/example"),
        junit_path=Path("test-results/example-junit.xml"),
        coverage=True,
    )

    assert command[0] == sys.executable
    assert "-m" in command
    assert "pytest" in command
    assert "python/example" in command
    assert "--junitxml=test-results/example-junit.xml" in command
    assert "--cov" in command


def test_build_cargo_command_workspace() -> None:
    command = build_cargo_command()

    assert command[0] == "cargo"
    assert command[1] == "test"
    assert "--workspace" in command


def test_build_cargo_command_specific_crate() -> None:
    command = build_cargo_command(crate="apex-testkit")

    assert "--package" in command
    assert "apex-testkit" in command