from pathlib import Path

import pytest

from apexquant_backup_recovery.models import (
    BackupPolicy,
    RestoreStatus,
    TargetSystem,
)
from apexquant_backup_recovery.repository import InMemoryBackupRepository
from apexquant_backup_recovery.runner import CommandResult
from apexquant_backup_recovery.service import BackupService
from apexquant_backup_recovery.storage import LocalDirectoryStorage


class FakeCommandRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, command, timeout=None) -> CommandResult:
        command = list(command)
        self.commands.append(command)

        for arg in command:
            if arg.startswith("--file="):
                output_path = Path(arg.split("=", 1)[1])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"backup-payload")

        return CommandResult(returncode=0, stdout="", stderr="")


@pytest.fixture
def service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BackupService:
    repository = InMemoryBackupRepository()
    storage = LocalDirectoryStorage(root=tmp_path / "storage", bucket="backups")
    runner = FakeCommandRunner()

    monkeypatch.setenv("TEST_BACKUP_DB_URL", "postgres://user:pass@localhost:5432/apexquant")
    monkeypatch.setenv("TEST_RESTORE_DB_URL", "postgres://user:pass@localhost:5432/restored")

    return BackupService(
        repository=repository,
        storage=storage,
        runner=runner,
        environment="local",
        workdir=tmp_path / "work",
    )


def postgres_policy() -> BackupPolicy:
    return BackupPolicy(
        name="local-postgres",
        target_system=TargetSystem.POSTGRES,
        target_name="apexquant",
        target_connection_ref="env://TEST_BACKUP_DB_URL",
        storage_bucket="backups",
        interval_minutes=1440,
        retention_count=2,
        retention_days=7,
    )


def test_backup_verify_restore_retention_flow(service: BackupService) -> None:
    policy = service.create_policy(postgres_policy())

    first_run = service.create_backup(policy.policy_id)

    assert first_run.status.value == "SUCCEEDED"
    assert first_run.checksum_sha256 is not None
    assert first_run.artifact_uri is not None

    verified_run = service.verify_backup(first_run.run_id)

    assert verified_run.verification_status == "SUCCEEDED"

    second_run = service.create_backup(policy.policy_id)
    third_run = service.create_backup(policy.policy_id)

    expired = service.apply_retention(policy.policy_id)

    active_artifacts = [
        artifact
        for artifact in service._repository.list_artifacts(policy.policy_id)
        if artifact.status.value == "ACTIVE"
    ]

    assert len(active_artifacts) == 2
    assert len(expired) == 1

    restore = service.restore_backup(
        run_id=third_run.run_id,
        target_connection_ref="env://TEST_RESTORE_DB_URL",
        dry_run=True,
    )

    assert restore.status == RestoreStatus.DRY_RUN
    assert restore.command_redacted is not None
    assert "postgres://user:***@localhost:5432/restored" in restore.command_redacted