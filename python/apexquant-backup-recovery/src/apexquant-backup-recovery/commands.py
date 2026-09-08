from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from apexquant_backup_recovery.errors import UnsupportedTargetError
from apexquant_backup_recovery.models import BackupPolicy, TargetSystem


@dataclass
class BackupCommand:
    command: list[str]
    output_path: Path


def build_backup_command(
    policy: BackupPolicy,
    workdir: Path,
    run_id: str,
    resolved_connection: str,
) -> BackupCommand:
    if policy.target_system != TargetSystem.POSTGRES:
        raise UnsupportedTargetError(
            "Phase 0 backup executor supports PostgreSQL targets only; "
            "additional targets are introduced in later reliability features"
        )

    output_path = workdir / f"{policy.target_name}-{run_id}.dump"

    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        f"--file={output_path}",
        resolved_connection,
    ]

    return BackupCommand(command=command, output_path=output_path)


def build_verify_command(backup_file: Path) -> list[str]:
    return [
        "pg_restore",
        "--list",
        str(backup_file),
    ]


def build_restore_command(
    backup_file: Path,
    resolved_target_connection: str,
) -> list[str]:
    return [
        "pg_restore",
        "--no-owner",
        "--no-privileges",
        "--clean",
        "--if-exists",
        f"--dbname={resolved_target_connection}",
        str(backup_file),
    ]