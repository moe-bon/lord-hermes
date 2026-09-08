from pathlib import Path

import pytest

from apexquant_backup_recovery.commands import (
    build_backup_command,
    build_restore_command,
    build_verify_command,
)
from apexquant_backup_recovery.errors import UnsupportedTargetError
from apexquant_backup_recovery.models import BackupPolicy, TargetSystem


def postgres_policy() -> BackupPolicy:
    return BackupPolicy(
        name="local-postgres",
        target_system=TargetSystem.POSTGRES,
        target_name="apexquant",
        target_connection_ref="env://TEST_BACKUP_DB_URL",
        storage_bucket="backups",
    )


def test_build_backup_command() -> None:
    policy = postgres_policy()

    command = build_backup_command(
        policy=policy,
        workdir=Path("/tmp/work"),
        run_id="run-123",
        resolved_connection="postgres://user:pass@localhost:5432/apexquant",
    )

    assert command.command[0] == "pg_dump"
    assert "--format=custom" in command.command
    assert "--no-owner" in command.command
    assert "--no-privileges" in command.command
    assert str(command.output_path).endswith("apexquant-run-123.dump")


def test_build_restore_command() -> None:
    command = build_restore_command(
        backup_file=Path("/tmp/backup.dump"),
        resolved_target_connection="postgres://user:pass@localhost:5432/restored",
    )

    assert command[0] == "pg_restore"
    assert "--clean" in command
    assert "--if-exists" in command


def test_build_verify_command() -> None:
    command = build_verify_command(Path("/tmp/backup.dump"))

    assert command[0] == "pg_restore"
    assert "--list" in command


def test_non_postgres_target_is_explicitly_unsupported() -> None:
    policy = BackupPolicy(
        name="local-clickhouse",
        target_system=TargetSystem.CLICKHOUSE,
        target_name="analytics",
        target_connection_ref="env://CLICKHOUSE_URL",
        storage_bucket="backups",
    )

    with pytest.raises(UnsupportedTargetError):
        build_backup_command(
            policy=policy,
            workdir=Path("/tmp/work"),
            run_id="run-123",
            resolved_connection="clickhouse://localhost:9000",
        )