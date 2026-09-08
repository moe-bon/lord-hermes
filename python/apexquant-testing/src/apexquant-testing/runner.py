from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from apexquant_testing.models import TestCaseResult, TestRunReport, TestStatus
from apexquant_testing.parser import parse_junit_file


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def git_sha(root: Path | str = ".") -> str | None:
    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            stderr=subprocess.DEVNULL,
        )
        return output.decode("utf-8").strip()
    except Exception:
        return None


def build_pytest_command(
    package_dir: Path,
    junit_path: Path,
    coverage: bool = False,
    extra_args: list[str] | None = None,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        str(package_dir),
        f"--junitxml={junit_path}",
        "-q",
    ]

    if coverage:
        command.extend(["--cov", "--cov-report=xml"])

    if extra_args:
        command.extend(extra_args)

    return command


def build_cargo_command(
    crate: str | None = None,
    extra_args: list[str] | None = None,
) -> list[str]:
    command = ["cargo", "test"]

    if crate:
        command.extend(["--package", crate])
    else:
        command.append("--workspace")

    if extra_args:
        command.extend(extra_args)

    return command


def run_python_tests(
    package_dir: Path | str,
    output_dir: Path | str,
    coverage: bool = False,
    extra_args: list[str] | None = None,
) -> list[TestCaseResult]:
    package_dir = Path(package_dir).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    junit_path = output_dir / f"{package_dir.name}-junit.xml"

    command = build_pytest_command(
        package_dir=package_dir,
        junit_path=junit_path,
        coverage=coverage,
        extra_args=extra_args,
    )

    completed = subprocess.run(
        command,
        cwd=package_dir,
        capture_output=True,
        text=True,
    )

    results = parse_junit_file(junit_path)

    if results:
        return results

    status = TestStatus.PASSED if completed.returncode == 0 else TestStatus.ERROR

    return [
        TestCaseResult(
            suite=package_dir.name,
            name="pytest",
            status=status,
            duration_ms=0.0,
            message=(completed.stdout or completed.stderr)[-2000:],
            details={
                "returncode": completed.returncode,
                "command": command,
            },
        )
    ]


def run_rust_tests(
    output_dir: Path | str,
    crate: str | None = None,
) -> list[TestCaseResult]:
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    command = build_cargo_command(crate=crate)

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    status = TestStatus.PASSED if completed.returncode == 0 else TestStatus.ERROR

    name = "cargo-test" if crate is None else f"cargo-test:{crate}"

    return [
        TestCaseResult(
            suite="rust",
            name=name,
            status=status,
            duration_ms=0.0,
            message=(completed.stdout or completed.stderr)[-2000:],
            details={
                "returncode": completed.returncode,
                "command": command,
            },
        )
    ]


def discover_python_packages(root: Path | str) -> list[Path]:
    root = Path(root).resolve()
    python_root = root / "python"

    if not python_root.exists():
        return []

    packages: list[Path] = []

    for pyproject in sorted(python_root.glob("*/pyproject.toml")):
        package_dir = pyproject.parent

        if (package_dir / "tests").exists():
            packages.append(package_dir)

    return packages


def run_all(
    python_packages: list[Path | str],
    *,
    rust_enabled: bool = False,
    rust_crate: str | None = None,
    output_dir: Path | str = "test-results",
    environment: str = "local",
    trigger: str = "manual",
    coverage: bool = False,
) -> TestRunReport:
    started_at = utc_now()

    results: list[TestCaseResult] = []

    for package in python_packages:
        results.extend(
            run_python_tests(
                package_dir=package,
                output_dir=output_dir,
                coverage=coverage,
            )
        )

    if rust_enabled:
        results.extend(
            run_rust_tests(
                output_dir=output_dir,
                crate=rust_crate,
            )
        )

    completed_at = utc_now()

    return TestRunReport.from_results(
        results=results,
        environment=environment,
        git_sha=git_sha(),
        trigger=trigger,
        started_at=started_at,
        completed_at=completed_at,
    )