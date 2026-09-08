from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from uuid import UUID

from apexquant_backup_recovery.checksum import sha256_file
from apexquant_backup_recovery.commands import (
    build_backup_command,
    build_restore_command,
    build_verify_command,
)
from apexquant_backup_recovery.errors import (
    BackupError,
    BackupNotFoundError,
    RestoreSafetyError,
)
from apexquant_backup_recovery.models import (
    ArtifactStatus,
    BackupArtifact,
    BackupPolicy,
    BackupRun,
    BackupRunStatus,
    RestoreRun,
    RestoreStatus,
    utc_now,
)
from apexquant_backup_recovery.redaction import redact_command, redact_url
from apexquant_backup_recovery.repository import BackupRepository
from apexquant_backup_recovery.runner import CommandRunner
from apexquant_backup_recovery.secret_refs import resolve_connection_ref
from apexquant_backup_recovery.storage import ObjectStorageClient


class BackupService:
    def __init__(
        self,
        repository: BackupRepository,
        storage: ObjectStorageClient,
        runner: CommandRunner,
        environment: str,
        workdir: Path,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._runner = runner
        self._environment = environment
        self._workdir = Path(workdir)

        self._workdir.mkdir(parents=True, exist_ok=True)

    def create_policy(self, policy: BackupPolicy) -> BackupPolicy:
        if policy.enabled and policy.next_run_at is None:
            policy.next_run_at = utc_now() + timedelta(minutes=policy.interval_minutes)

        return self._repository.create_policy(policy)

    def get_policy_by_name(self, name: str) -> BackupPolicy | None:
        return self._repository.get_policy_by_name(name)

    def list_policies(self) -> list[BackupPolicy]:
        return self._repository.list_policies()

    def create_backup(self, policy_id: UUID, trigger: str = "manual") -> BackupRun:
        policy = self._repository.get_policy(policy_id)

        if policy is None:
            raise BackupNotFoundError(f"backup policy not found: {policy_id}")

        if not policy.enabled:
            raise BackupError(f"backup policy is disabled: {policy.name}")

        run = BackupRun(
            policy_id=policy_id,
            trigger=trigger,
            status=BackupRunStatus.RUNNING,
            started_at=utc_now(),
        )

        run = self._repository.create_run(run)

        try:
            resolved_connection = resolve_connection_ref(policy.target_connection_ref)

            backup_command = build_backup_command(
                policy=policy,
                workdir=self._workdir,
                run_id=str(run.run_id),
                resolved_connection=resolved_connection,
            )

            self._runner.run(
                backup_command.command,
                timeout=policy.backup_timeout_seconds,
            )

            checksum = sha256_file(backup_command.output_path)
            size_bytes = backup_command.output_path.stat().st_size

            storage_key = (
                f"{policy.storage_prefix.strip('/')}/"
                f"{policy.target_system.value.lower()}/"
                f"{policy.target_name}/"
                f"{run.run_id}.dump"
            )

            uri = self._storage.upload_file(backup_command.output_path, storage_key)

            expires_at = None

            if policy.retention_days is not None:
                expires_at = utc_now() + timedelta(days=policy.retention_days)

            artifact = BackupArtifact(
                run_id=run.run_id,
                policy_id=policy_id,
                target_system=policy.target_system,
                target_name=policy.target_name,
                storage_key=storage_key,
                uri=uri,
                size_bytes=size_bytes,
                checksum_sha256=checksum,
                encryption_key_ref=policy.encryption_key_ref,
                status=ArtifactStatus.ACTIVE,
                created_at=utc_now(),
                expires_at=expires_at,
            )

            self._repository.create_artifact(artifact)

            run.status = BackupRunStatus.SUCCEEDED
            run.completed_at = utc_now()
            run.artifact_uri = uri
            run.artifact_size_bytes = size_bytes
            run.checksum_sha256 = checksum

            self._repository.update_run(run)

            if policy.enabled and policy.interval_minutes:
                self._repository.update_policy_next_run(
                    policy_id,
                    utc_now() + timedelta(minutes=policy.interval_minutes),
                )

            return run
        except Exception as exc:
            run.status = BackupRunStatus.FAILED
            run.completed_at = utc_now()
            run.error = str(exc)

            self._repository.update_run(run)

            raise BackupError(str(exc)) from exc

    def verify_backup(self, run_id: UUID) -> BackupRun:
        run = self._repository.get_run(run_id)

        if run is None:
            raise BackupNotFoundError(f"backup run not found: {run_id}")

        artifact = self._repository.get_artifact_by_run(run_id)

        if artifact is None:
            raise BackupNotFoundError(f"backup artifact not found for run: {run_id}")

        policy = self._repository.get_policy(run.policy_id)

        if policy is None:
            raise BackupNotFoundError(f"backup policy not found: {run.policy_id}")

        local_path = self._workdir / f"verify-{run_id}.dump"

        try:
            self._storage.download_file(artifact.storage_key, local_path)

            checksum = sha256_file(local_path)

            if checksum != artifact.checksum_sha256:
                raise BackupError(
                    "backup artifact checksum mismatch; backup is corrupt"
                )

            command = build_verify_command(local_path)

            self._runner.run(command, timeout=policy.backup_timeout_seconds)

            run.verification_status = "SUCCEEDED"
            run.last_verified_at = utc_now()

            self._repository.update_run(run)

            return run
        except Exception as exc:
            run.verification_status = "FAILED"
            run.error = str(exc)

            self._repository.update_run(run)

            raise BackupError(str(exc)) from exc

    def restore_backup(
        self,
        run_id: UUID,
        target_connection_ref: str,
        dry_run: bool = True,
        confirm: bool = False,
        allow_production_restore: bool = False,
    ) -> RestoreRun:
        run = self._repository.get_run(run_id)

        if run is None:
            raise BackupNotFoundError(f"backup run not found: {run_id}")

        if run.status != BackupRunStatus.SUCCEEDED:
            raise BackupError("only succeeded backup runs may be restored")

        artifact = self._repository.get_artifact_by_run(run_id)

        if artifact is None:
            raise BackupNotFoundError(f"backup artifact not found for run: {run_id}")

        if self._environment == "production" and not allow_production_restore:
            raise RestoreSafetyError(
                "production restores require explicit allow_production_restore"
            )

        if not dry_run and not confirm:
            raise RestoreSafetyError(
                "restore execution requires confirm=true; default is dry-run"
            )

        resolved_target_connection = resolve_connection_ref(target_connection_ref)

        local_path = self._workdir / f"restore-{run_id}.dump"

        self._storage.download_file(artifact.storage_key, local_path)

        checksum = sha256_file(local_path)

        if checksum != artifact.checksum_sha256:
            raise BackupError("backup artifact checksum mismatch; refusing restore")

        command = build_restore_command(local_path, resolved_target_connection)
        redacted_command = redact_command(command)

        restore = RestoreRun(
            backup_run_id=run_id,
            target_connection_ref=target_connection_ref,
            target_connection_redacted=redact_url(resolved_target_connection),
            command_redacted=" ".join(redacted_command),
            status=RestoreStatus.DRY_RUN if dry_run else RestoreStatus.RUNNING,
            dry_run=dry_run,
            started_at=utc_now(),
        )

        restore = self._repository.create_restore(restore)

        if dry_run:
            restore.completed_at = utc_now()
            self._repository.update_restore(restore)

            return restore

        try:
            self._runner.run(command)

            restore.status = RestoreStatus.SUCCEEDED
            restore.completed_at = utc_now()

            self._repository.update_restore(restore)

            return restore
        except Exception as exc:
            restore.status = RestoreStatus.FAILED
            restore.completed_at = utc_now()
            restore.error = str(exc)

            self._repository.update_restore(restore)

            raise BackupError(str(exc)) from exc

    def apply_retention(self, policy_id: UUID) -> list[BackupArtifact]:
        policy = self._repository.get_policy(policy_id)

        if policy is None:
            raise BackupNotFoundError(f"backup policy not found: {policy_id}")

        artifacts = self._repository.list_artifacts(policy_id)

        active = [
            artifact
            for artifact in artifacts
            if artifact.status == ArtifactStatus.ACTIVE
        ]

        active.sort(key=lambda artifact: artifact.created_at, reverse=True)

        expired: list[BackupArtifact] = []
        now = utc_now()

        for index, artifact in enumerate(active):
            expired_by_count = (
                policy.retention_count is not None and index >= policy.retention_count
            )

            expired_by_age = (
                policy.retention_days is not None
                and artifact.expires_at is not None
                and artifact.expires_at <= now
            )

            if expired_by_count or expired_by_age:
                expired.append(artifact)

        for artifact in expired:
            self._repository.update_artifact_status(
                artifact.artifact_id,
                ArtifactStatus.EXPIRED,
            )

            if policy.delete_expired:
                self._storage.delete_object(artifact.storage_key)

                self._repository.update_artifact_status(
                    artifact.artifact_id,
                    ArtifactStatus.DELETED,
                )

        return expired

    def run_due(self) -> list[BackupRun]:
        now = utc_now()
        due_policies = [
            policy
            for policy in self._repository.list_policies()
            if policy.enabled
            and policy.next_run_at is not None
            and policy.next_run_at <= now
        ]

        runs: list[BackupRun] = []

        for policy in due_policies:
            try:
                runs.append(self.create_backup(policy.policy_id, trigger="scheduled"))
            except BackupError:
                continue

        return runs