from __future__ import annotations

import tomllib
from datetime import datetime, timezone
from pathlib import Path

from apexquant_repo_architecture.models import (
    PathKind,
    RequiredPath,
    Severity,
    VerificationReport,
    Violation,
)

REQUIRED_DIRS: tuple[RequiredPath, ...] = (
    RequiredPath(
        path=".github/workflows",
        kind=PathKind.DIR,
        description="CI workflows",
    ),
    RequiredPath(
        path="docs",
        kind=PathKind.DIR,
        description="Documentation root",
    ),
    RequiredPath(
        path="proto/apexquant/common/v1",
        kind=PathKind.DIR,
        description="Common Protobuf contracts",
    ),
    RequiredPath(
        path="openapi",
        kind=PathKind.DIR,
        description="OpenAPI contracts",
    ),
    RequiredPath(
        path="crates/common",
        kind=PathKind.DIR,
        description="Shared Rust crates",
    ),
    RequiredPath(
        path="crates/control",
        kind=PathKind.DIR,
        description="Control-plane Rust crates",
    ),
    RequiredPath(
        path="crates/market_data",
        kind=PathKind.DIR,
        description="Market-data Rust crates",
    ),
    RequiredPath(
        path="crates/broker",
        kind=PathKind.DIR,
        description="Broker Rust crates",
    ),
    RequiredPath(
        path="crates/orders",
        kind=PathKind.DIR,
        description="Order Rust crates",
    ),
    RequiredPath(
        path="crates/execution",
        kind=PathKind.DIR,
        description="Execution Rust crates",
    ),
    RequiredPath(
        path="crates/positions",
        kind=PathKind.DIR,
        description="Position Rust crates",
    ),
    RequiredPath(
        path="crates/reconciliation",
        kind=PathKind.DIR,
        description="Reconciliation Rust crates",
    ),
    RequiredPath(
        path="crates/risk",
        kind=PathKind.DIR,
        description="Risk Rust crates",
    ),
    RequiredPath(
        path="crates/ledger",
        kind=PathKind.DIR,
        description="Ledger Rust crates",
    ),
    RequiredPath(
        path="crates/telemetry",
        kind=PathKind.DIR,
        description="Telemetry Rust crates",
    ),
    RequiredPath(
        path="crates/testing",
        kind=PathKind.DIR,
        description="Testing Rust crates",
    ),
    RequiredPath(
        path="python",
        kind=PathKind.DIR,
        description="Python packages",
    ),
    RequiredPath(
        path="services/control",
        kind=PathKind.DIR,
        description="Control-plane services",
    ),
    RequiredPath(
        path="services/market_data",
        kind=PathKind.DIR,
        description="Market-data services",
    ),
    RequiredPath(
        path="services/broker",
        kind=PathKind.DIR,
        description="Broker services",
    ),
    RequiredPath(
        path="services/trading",
        kind=PathKind.DIR,
        description="Trading services",
    ),
    RequiredPath(
        path="services/risk",
        kind=PathKind.DIR,
        description="Risk services",
    ),
    RequiredPath(
        path="services/ledger",
        kind=PathKind.DIR,
        description="Ledger services",
    ),
    RequiredPath(
        path="services/strategy",
        kind=PathKind.DIR,
        description="Strategy services",
    ),
    RequiredPath(
        path="services/intelligence",
        kind=PathKind.DIR,
        description="Intelligence services",
    ),
    RequiredPath(
        path="services/decision",
        kind=PathKind.DIR,
        description="Decision services",
    ),
    RequiredPath(
        path="services/portfolio",
        kind=PathKind.DIR,
        description="Portfolio services",
    ),
    RequiredPath(
        path="services/routing",
        kind=PathKind.DIR,
        description="Routing services",
    ),
    RequiredPath(
        path="services/news_events",
        kind=PathKind.DIR,
        description="News and event services",
    ),
    RequiredPath(
        path="services/knowledge",
        kind=PathKind.DIR,
        description="Knowledge services",
    ),
    RequiredPath(
        path="services/learning",
        kind=PathKind.DIR,
        description="Continuous-learning services",
    ),
    RequiredPath(
        path="services/research",
        kind=PathKind.DIR,
        description="Research services",
    ),
    RequiredPath(
        path="services/reliability",
        kind=PathKind.DIR,
        description="Reliability services",
    ),
    RequiredPath(
        path="services/security",
        kind=PathKind.DIR,
        description="Security services",
    ),
    RequiredPath(
        path="services/observability",
        kind=PathKind.DIR,
        description="Observability services",
    ),
    RequiredPath(
        path="services/reporting",
        kind=PathKind.DIR,
        description="Reporting services",
    ),
    RequiredPath(
        path="apps",
        kind=PathKind.DIR,
        description="User applications",
    ),
    RequiredPath(
        path="ai",
        kind=PathKind.DIR,
        description="AI artifacts and governance",
    ),
    RequiredPath(
        path="backtesting",
        kind=PathKind.DIR,
        description="Backtesting engine assets",
    ),
    RequiredPath(
        path="data",
        kind=PathKind.DIR,
        description="Data schemas and contracts",
    ),
    RequiredPath(
        path="migrations/postgres",
        kind=PathKind.DIR,
        description="PostgreSQL migrations",
    ),
    RequiredPath(
        path="migrations/clickhouse",
        kind=PathKind.DIR,
        description="ClickHouse migrations",
    ),
    RequiredPath(
        path="migrations/qdrant",
        kind=PathKind.DIR,
        description="Qdrant collections",
    ),
    RequiredPath(
        path="migrations/kafka",
        kind=PathKind.DIR,
        description="Kafka topic definitions",
    ),
    RequiredPath(
        path="infra/docker/dockerfiles",
        kind=PathKind.DIR,
        description="Dockerfiles",
    ),
    RequiredPath(
        path="infra/docker/compose/local",
        kind=PathKind.DIR,
        description="Local Docker Compose stack",
    ),
    RequiredPath(
        path="infra/kubernetes",
        kind=PathKind.DIR,
        description="Kubernetes manifests",
    ),
    RequiredPath(
        path="infra/helm",
        kind=PathKind.DIR,
        description="Helm charts",
    ),
    RequiredPath(
        path="infra/opentofu",
        kind=PathKind.DIR,
        description="OpenTofu infrastructure",
    ),
    RequiredPath(
        path="infra/ansible",
        kind=PathKind.DIR,
        description="Ansible automation",
    ),
    RequiredPath(
        path="infra/monitoring/prometheus",
        kind=PathKind.DIR,
        description="Prometheus configuration",
    ),
    RequiredPath(
        path="infra/security",
        kind=PathKind.DIR,
        description="Security infrastructure",
    ),
    RequiredPath(
        path="infra/environments",
        kind=PathKind.DIR,
        description="Environment definitions",
    ),
    RequiredPath(
        path="templates",
        kind=PathKind.DIR,
        description="Feature and service templates",
    ),
    RequiredPath(
        path="tests",
        kind=PathKind.DIR,
        description="Cross-service tests",
    ),
    RequiredPath(
        path="scripts",
        kind=PathKind.DIR,
        description="Automation scripts",
    ),
)

REQUIRED_FILES: tuple[RequiredPath, ...] = (
    RequiredPath(
        path="Cargo.toml",
        kind=PathKind.FILE,
        description="Rust workspace manifest",
    ),
    RequiredPath(
        path="rust-toolchain.toml",
        kind=PathKind.FILE,
        description="Rust toolchain pin",
    ),
    RequiredPath(
        path="pyproject.toml",
        kind=PathKind.FILE,
        description="Root Python tooling manifest",
    ),
    RequiredPath(
        path="Makefile",
        kind=PathKind.FILE,
        description="Repository automation entrypoint",
    ),
    RequiredPath(
        path="README.md",
        kind=PathKind.FILE,
        description="Repository README",
    ),
    RequiredPath(
        path="buf.yaml",
        kind=PathKind.FILE,
        description="Protobuf workspace configuration",
    ),
    RequiredPath(
        path="buf.gen.yaml",
        kind=PathKind.FILE,
        description="Protobuf generation configuration",
    ),
    RequiredPath(
        path=".gitignore",
        kind=PathKind.FILE,
        description="Git ignore rules",
    ),
    RequiredPath(
        path=".gitattributes",
        kind=PathKind.FILE,
        description="Git attribute rules",
    ),
    RequiredPath(
        path=".editorconfig",
        kind=PathKind.FILE,
        description="Editor configuration",
    ),
    RequiredPath(
        path=".rustfmt.toml",
        kind=PathKind.FILE,
        description="Rust formatting rules",
    ),
    RequiredPath(
        path="clippy.toml",
        kind=PathKind.FILE,
        description="Rust lint configuration",
    ),
    RequiredPath(
        path=".github/workflows/ci.yml",
        kind=PathKind.FILE,
        description="CI workflow",
    ),
    RequiredPath(
        path="proto/apexquant/common/v1/service_framework.proto",
        kind=PathKind.FILE,
        description="Service framework Protobuf contract",
    ),
    RequiredPath(
        path="migrations/postgres/service_framework/0001_service_framework.sql",
        kind=PathKind.FILE,
        description="Feature 0.1 PostgreSQL migration",
    ),
    RequiredPath(
        path="migrations/postgres/repository_architecture/0001_repository_architecture.sql",
        kind=PathKind.FILE,
        description="Feature 0.2 PostgreSQL migration",
    ),
    RequiredPath(
        path="migrations/clickhouse/service_framework/0001_service_framework.sql",
        kind=PathKind.FILE,
        description="Feature 0.1 ClickHouse migration",
    ),
    RequiredPath(
        path="crates/control/service-framework-core/Cargo.toml",
        kind=PathKind.FILE,
        description="Feature 0.1 Rust crate manifest",
    ),
    RequiredPath(
        path="python/apexquant-service-framework/pyproject.toml",
        kind=PathKind.FILE,
        description="Feature 0.1 Python package manifest",
    ),
    RequiredPath(
        path="python/apexquant-repo-architecture/pyproject.toml",
        kind=PathKind.FILE,
        description="Feature 0.2 Python package manifest",
    ),
    RequiredPath(
        path="infra/docker/dockerfiles/Dockerfile.service-framework",
        kind=PathKind.FILE,
        description="Feature 0.1 service Dockerfile",
    ),
    RequiredPath(
        path="infra/docker/dockerfiles/Dockerfile.repo-architecture-verifier",
        kind=PathKind.FILE,
        description="Feature 0.2 repository verifier Dockerfile",
    ),
    RequiredPath(
        path="infra/docker/compose/local/docker-compose.yaml",
        kind=PathKind.FILE,
        description="Local Docker Compose stack",
    ),
    RequiredPath(
        path="infra/monitoring/prometheus/prometheus.yml",
        kind=PathKind.FILE,
        description="Prometheus configuration",
    ),
)

ALLOWED_TOP_LEVEL: frozenset[str] = frozenset(
    {
        ".git",
        ".github",
        ".editorconfig",
        ".gitattributes",
        ".gitignore",
        ".rustfmt.toml",
        "clippy.toml",
        "Cargo.toml",
        "Cargo.lock",
        "rust-toolchain.toml",
        "pyproject.toml",
        "uv.lock",
        "Makefile",
        "README.md",
        "LICENSE",
        "buf.yaml",
        "buf.gen.yaml",
        "buf.lock",
        ".pre-commit-config.yaml",
        "docs",
        "proto",
        "openapi",
        "crates",
        "python",
        "services",
        "apps",
        "ai",
        "backtesting",
        "data",
        "migrations",
        "infra",
        "templates",
        "tests",
        "scripts",
        "target",
        ".venv",
        "node_modules",
    }
)

REQUIRED_WORKSPACE_MEMBER = "crates/control/service-framework-core"


def scan_repo(repo_root: Path, *, strict_warnings: bool = False) -> VerificationReport:
    started_at = datetime.now(timezone.utc)
    violations: list[Violation] = []
    checked_paths: list[str] = []

    if not repo_root.exists() or not repo_root.is_dir():
        violations.append(
            Violation(
                code="MISSING_REPOSITORY_ROOT",
                severity=Severity.ERROR,
                path=str(repo_root),
                message="repository root does not exist or is not a directory",
            )
        )

        completed_at = datetime.now(timezone.utc)

        return VerificationReport(
            repo_root=str(repo_root),
            started_at=started_at,
            completed_at=completed_at,
            ok=False,
            errors_count=1,
            warnings_count=0,
            violations=violations,
            checked_paths=checked_paths,
            cargo_members=[],
            python_packages=[],
        )

    _check_required_paths(repo_root, violations, checked_paths)
    cargo_members = _load_cargo_members(repo_root, violations)
    _check_cargo_members(repo_root, cargo_members, violations)
    python_packages = _scan_python_packages(repo_root, violations)
    _check_top_level(repo_root, violations)

    completed_at = datetime.now(timezone.utc)

    errors_count = sum(1 for violation in violations if violation.severity == Severity.ERROR)
    warnings_count = sum(1 for violation in violations if violation.severity == Severity.WARNING)

    ok = errors_count == 0 and (not strict_warnings or warnings_count == 0)

    return VerificationReport(
        repo_root=str(repo_root),
        started_at=started_at,
        completed_at=completed_at,
        ok=ok,
        errors_count=errors_count,
        warnings_count=warnings_count,
        violations=violations,
        checked_paths=checked_paths,
        cargo_members=cargo_members,
        python_packages=python_packages,
    )


def _check_required_paths(
    repo_root: Path,
    violations: list[Violation],
    checked_paths: list[str],
) -> None:
    for required in (*REQUIRED_DIRS, *REQUIRED_FILES):
        target = repo_root / required.path
        checked_paths.append(required.path)

        if required.kind == PathKind.DIR:
            if not target.is_dir():
                violations.append(
                    Violation(
                        code="MISSING_DIRECTORY",
                        severity=Severity.ERROR,
                        path=required.path,
                        message=f"required directory is missing: {required.description}",
                    )
                )
            continue

        if not target.is_file():
            violations.append(
                Violation(
                    code="MISSING_FILE",
                    severity=Severity.ERROR,
                    path=required.path,
                    message=f"required file is missing: {required.description}",
                )
            )


def _load_cargo_members(repo_root: Path, violations: list[Violation]) -> list[str]:
    cargo_toml = repo_root / "Cargo.toml"

    if not cargo_toml.is_file():
        return []

    try:
        raw = tomllib.loads(cargo_toml.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        violations.append(
            Violation(
                code="INVALID_CARGO_TOML",
                severity=Severity.ERROR,
                path="Cargo.toml",
                message=f"root Cargo.toml could not be parsed: {exc}",
            )
        )
        return []

    workspace = raw.get("workspace")
    if not isinstance(workspace, dict):
        violations.append(
            Violation(
                code="MISSING_WORKSPACE_SECTION",
                severity=Severity.ERROR,
                path="Cargo.toml",
                message="root Cargo.toml must define [workspace]",
            )
        )
        return []

    members = workspace.get("members")
    if not isinstance(members, list):
        violations.append(
            Violation(
                code="MISSING_WORKSPACE_MEMBERS",
                severity=Severity.ERROR,
                path="Cargo.toml",
                message="[workspace].members must be a list",
            )
        )
        return []

    normalized_members: list[str] = []

    for member in members:
        if not isinstance(member, str):
            violations.append(
                Violation(
                    code="INVALID_WORKSPACE_MEMBER",
                    severity=Severity.ERROR,
                    path="Cargo.toml",
                    message="workspace members must be strings",
                )
            )
            continue

        normalized_members.append(member)

    if REQUIRED_WORKSPACE_MEMBER not in normalized_members:
        violations.append(
            Violation(
                code="MISSING_WORKSPACE_MEMBER",
                severity=Severity.ERROR,
                path="Cargo.toml",
                message=(
                    "workspace must include "
                    f"{REQUIRED_WORKSPACE_MEMBER}"
                ),
            )
        )

    return normalized_members


def _check_cargo_members(
    repo_root: Path,
    cargo_members: list[str],
    violations: list[Violation],
) -> None:
    for member in cargo_members:
        if "*" in member:
            violations.append(
                Violation(
                    code="UNSUPPORTED_WORKSPACE_GLOB",
                    severity=Severity.ERROR,
                    path="Cargo.toml",
                    message=f"workspace member glob patterns are not allowed: {member}",
                )
            )
            continue

        member_manifest = repo_root / member / "Cargo.toml"

        if not member_manifest.is_file():
            violations.append(
                Violation(
                    code="MISSING_CARGO_MANIFEST",
                    severity=Severity.ERROR,
                    path=f"{member}/Cargo.toml",
                    message="workspace member does not contain a Cargo.toml manifest",
                )
            )


def _scan_python_packages(repo_root: Path, violations: list[Violation]) -> list[str]:
    python_root = repo_root / "python"

    if not python_root.is_dir():
        return []

    packages: list[str] = []

    for child in sorted(python_root.iterdir()):
        if not child.is_dir():
            continue

        if child.name.startswith("."):
            continue

        if child.name in {"generated", "__pycache__"}:
            continue

        packages.append(child.name)

        if not (child / "pyproject.toml").is_file():
            violations.append(
                Violation(
                    code="MISSING_PYPROJECT",
                    severity=Severity.ERROR,
                    path=f"python/{child.name}/pyproject.toml",
                    message="Python package is missing pyproject.toml",
                )
            )

        if not (child / "src").is_dir():
            violations.append(
                Violation(
                    code="MISSING_SRC_LAYOUT",
                    severity=Severity.ERROR,
                    path=f"python/{child.name}/src",
                    message="Python package must use the src/ package layout",
                )
            )

    return packages


def _check_top_level(repo_root: Path, violations: list[Violation]) -> None:
    for entry in sorted(repo_root.iterdir()):
        if entry.name in ALLOWED_TOP_LEVEL:
            continue

        violations.append(
            Violation(
                code="UNEXPECTED_TOP_LEVEL_ENTRY",
                severity=Severity.WARNING,
                path=entry.name,
                message="unexpected top-level repository entry",
            )
        )