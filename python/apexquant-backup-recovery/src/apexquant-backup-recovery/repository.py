from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

import psycopg
from psycopg_pool import ConnectionPool

from apexquant_backup_recovery.models import (
    ArtifactStatus,
    BackupArtifact,
    BackupPolicy,
    BackupRun,
    RestoreRun,
    TargetSystem,
    new_uuid,
    utc_now,
)


class BackupRepositoryError(Exception):
    pass


def apply_migrations(database_url: str, migrations_dir: str) -> None:
    path = Path(migrations_dir)

    if not path.exists():
        raise BackupRepositoryError(f"migrations directory does not exist: {path}")

    migrations = sorted(path.glob("*.sql"))

    if not migrations:
        raise BackupRepositoryError(f"no SQL migrations found in {path}")

    with psycopg.connect(database_url, autocommit=True) as conn:
        for migration in migrations:
            conn.execute(migration.read_text(encoding="utf-8"))


class BackupRepository(Protocol):
    def create_policy(self, policy: BackupPolicy) -> BackupPolicy:
        raise NotImplementedError

    def get_policy(self, policy_id: UUID) -> BackupPolicy | None:
        raise NotImplementedError

    def get_policy_by_name(self, name: str) -> BackupPolicy | None:
        raise NotImplementedError

    def list_policies(self) -> list[BackupPolicy]:
        raise NotImplementedError

    def update_policy_next_run(self, policy_id: UUID, next_run_at: datetime) -> None:
        raise NotImplementedError

    def create_run(self, run: BackupRun) -> BackupRun:
        raise NotImplementedError

    def update_run(self, run: BackupRun) -> None:
        raise NotImplementedError

    def get_run(self, run_id: UUID) -> BackupRun | None:
        raise NotImplementedError

    def list_runs(self, policy_id: UUID | None = None, limit: int = 100) -> list[BackupRun]:
        raise NotImplementedError

    def create_artifact(self, artifact: BackupArtifact) -> BackupArtifact:
        raise NotImplementedError

    def list_artifacts(self, policy_id: UUID) -> list[BackupArtifact]:
        raise NotImplementedError

    def get_artifact_by_run(self, run_id: UUID) -> BackupArtifact | None:
        raise NotImplementedError

    def update_artifact_status(self, artifact_id: UUID, status: ArtifactStatus) -> None:
        raise NotImplementedError

    def create_restore(self, restore: RestoreRun) -> RestoreRun:
        raise NotImplementedError

    def update_restore(self, restore: RestoreRun) -> None:
        raise NotImplementedError


class InMemoryBackupRepository:
    def __init__(self) -> None:
        self._policies: dict[UUID, BackupPolicy] = {}
        self._runs: dict[UUID, BackupRun] = {}
        self._artifacts: dict[UUID, BackupArtifact] = {}
        self._restores: dict[UUID, RestoreRun] = {}

    def create_policy(self, policy: BackupPolicy) -> BackupPolicy:
        if policy.policy_id is None:
            policy.policy_id = new_uuid()

        now = utc_now()

        policy.created_at = policy.created_at or now
        policy.updated_at = now

        self._policies[policy.policy_id] = policy

        return policy

    def get_policy(self, policy_id: UUID) -> BackupPolicy | None:
        return self._policies.get(policy_id)

    def get_policy_by_name(self, name: str) -> BackupPolicy | None:
        for policy in self._policies.values():
            if policy.name == name:
                return policy

        return None

    def list_policies(self) -> list[BackupPolicy]:
        return sorted(self._policies.values(), key=lambda policy: policy.name)

    def update_policy_next_run(self, policy_id: UUID, next_run_at: datetime) -> None:
        policy = self._policies.get(policy_id)

        if policy is None:
            raise BackupRepositoryError(f"policy not found: {policy_id}")

        policy.next_run_at = next_run_at
        policy.updated_at = utc_now()

    def create_run(self, run: BackupRun) -> BackupRun:
        if run.run_id is None:
            run.run_id = new_uuid()

        self._runs[run.run_id] = run

        return run

    def update_run(self, run: BackupRun) -> None:
        if run.run_id is None:
            raise BackupRepositoryError("run has no run_id")

        self._runs[run.run_id] = run

    def get_run(self, run_id: UUID) -> BackupRun | None:
        return self._runs.get(run_id)

    def list_runs(self, policy_id: UUID | None = None, limit: int = 100) -> list[BackupRun]:
        runs = list(self._runs.values())

        if policy_id is not None:
            runs = [run for run in runs if run.policy_id == policy_id]

        runs.sort(key=lambda run: run.started_at, reverse=True)

        return runs[:limit]

    def create_artifact(self, artifact: BackupArtifact) -> BackupArtifact:
        if artifact.artifact_id is None:
            artifact.artifact_id = new_uuid()

        self._artifacts[artifact.artifact_id] = artifact

        return artifact

    def list_artifacts(self, policy_id: UUID) -> list[BackupArtifact]:
        artifacts = [
            artifact
            for artifact in self._artifacts.values()
            if artifact.policy_id == policy_id
        ]

        artifacts.sort(key=lambda artifact: artifact.created_at, reverse=True)

        return artifacts

    def get_artifact_by_run(self, run_id: UUID) -> BackupArtifact | None:
        for artifact in self._artifacts.values():
            if artifact.run_id == run_id:
                return artifact

        return None

    def update_artifact_status(self, artifact_id: UUID, status: ArtifactStatus) -> None:
        artifact = self._artifacts.get(artifact_id)

        if artifact is None:
            raise BackupRepositoryError(f"artifact not found: {artifact_id}")

        artifact.status = status

    def create_restore(self, restore: RestoreRun) -> RestoreRun:
        if restore.restore_id is None:
            restore.restore_id = new_uuid()

        self._restores[restore.restore_id] = restore

        return restore

    def update_restore(self, restore: RestoreRun) -> None:
        if restore.restore_id is None:
            raise BackupRepositoryError("restore has no restore_id")

        self._restores[restore.restore_id] = restore


class PostgresBackupRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def _policy_from_row(self, row) -> BackupPolicy:
        return BackupPolicy(
            policy_id=row[0],
            name=row[1],
            target_system=TargetSystem(row[2]),
            target_name=row[3],
            target_connection_ref=row[4],
            storage_bucket=row[5],
            storage_prefix=row[6],
            interval_minutes=row[7],
            backup_timeout_seconds=row[8],
            retention_count=row[9],
            retention_days=row[10],
            delete_expired=row[11],
            encryption_key_ref=row[12],
            enabled=row[13],
            next_run_at=row[14],
            created_at=row[15],
            updated_at=row[16],
        )

    def _run_from_row(self, row) -> BackupRun:
        return BackupRun(
            run_id=row[0],
            policy_id=row[1],
            trigger=row[2],
            status=row[3],
            started_at=row[4],
            completed_at=row[5],
            artifact_uri=row[6],
            artifact_size_bytes=row[7],
            checksum_sha256=row[8],
            error=row[9],
            verification_status=row[10],
            last_verified_at=row[11],
        )

    def _artifact_from_row(self, row) -> BackupArtifact:
        return BackupArtifact(
            artifact_id=row[0],
            run_id=row[1],
            policy_id=row[2],
            target_system=TargetSystem(row[3]),
            target_name=row[4],
            storage_key=row[5],
            uri=row[6],
            size_bytes=row[7],
            checksum_sha256=row[8],
            encryption_key_ref=row[9],
            status=ArtifactStatus(row[10]),
            created_at=row[11],
            expires_at=row[12],
        )

    def _restore_from_row(self, row) -> RestoreRun:
        return RestoreRun(
            restore_id=row[0],
            backup_run_id=row[1],
            target_connection_ref=row[2],
            target_connection_redacted=row[3],
            command_redacted=row[4],
            status=row[5],
            dry_run=row[6],
            started_at=row[7],
            completed_at=row[8],
            error=row[9],
        )

    def create_policy(self, policy: BackupPolicy) -> BackupPolicy:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO backup_recovery.backup_policies (
                    name,
                    target_system,
                    target_name,
                    target_connection_ref,
                    storage_bucket,
                    storage_prefix,
                    interval_minutes,
                    backup_timeout_seconds,
                    retention_count,
                    retention_days,
                    delete_expired,
                    encryption_key_ref,
                    enabled,
                    next_run_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING
                    policy_id,
                    name,
                    target_system,
                    target_name,
                    target_connection_ref,
                    storage_bucket,
                    storage_prefix,
                    interval_minutes,
                    backup_timeout_seconds,
                    retention_count,
                    retention_days,
                    delete_expired,
                    encryption_key_ref,
                    enabled,
                    next_run_at,
                    created_at,
                    updated_at
                """,
                (
                    policy.name,
                    policy.target_system.value,
                    policy.target_name,
                    policy.target_connection_ref,
                    policy.storage_bucket,
                    policy.storage_prefix,
                    policy.interval_minutes,
                    policy.backup_timeout_seconds,
                    policy.retention_count,
                    policy.retention_days,
                    policy.delete_expired,
                    policy.encryption_key_ref,
                    policy.enabled,
                    policy.next_run_at,
                ),
            ).fetchone()

        return self._policy_from_row(row)

    def get_policy(self, policy_id: UUID) -> BackupPolicy | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    policy_id,
                    name,
                    target_system,
                    target_name,
                    target_connection_ref,
                    storage_bucket,
                    storage_prefix,
                    interval_minutes,
                    backup_timeout_seconds,
                    retention_count,
                    retention_days,
                    delete_expired,
                    encryption_key_ref,
                    enabled,
                    next_run_at,
                    created_at,
                    updated_at
                FROM backup_recovery.backup_policies
                WHERE policy_id = %s
                """,
                (policy_id,),
            ).fetchone()

        if row is None:
            return None

        return self._policy_from_row(row)

    def get_policy_by_name(self, name: str) -> BackupPolicy | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    policy_id,
                    name,
                    target_system,
                    target_name,
                    target_connection_ref,
                    storage_bucket,
                    storage_prefix,
                    interval_minutes,
                    backup_timeout_seconds,
                    retention_count,
                    retention_days,
                    delete_expired,
                    encryption_key_ref,
                    enabled,
                    next_run_at,
                    created_at,
                    updated_at
                FROM backup_recovery.backup_policies
                WHERE name = %s
                """,
                (name,),
            ).fetchone()

        if row is None:
            return None

        return self._policy_from_row(row)

    def list_policies(self) -> list[BackupPolicy]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    policy_id,
                    name,
                    target_system,
                    target_name,
                    target_connection_ref,
                    storage_bucket,
                    storage_prefix,
                    interval_minutes,
                    backup_timeout_seconds,
                    retention_count,
                    retention_days,
                    delete_expired,
                    encryption_key_ref,
                    enabled,
                    next_run_at,
                    created_at,
                    updated_at
                FROM backup_recovery.backup_policies
                ORDER BY name
                """
            ).fetchall()

        return [self._policy_from_row(row) for row in rows]

    def update_policy_next_run(self, policy_id: UUID, next_run_at: datetime) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE backup_recovery.backup_policies
                SET
                    next_run_at = %s,
                    updated_at = now()
                WHERE policy_id = %s
                """,
                (next_run_at, policy_id),
            )

    def create_run(self, run: BackupRun) -> BackupRun:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO backup_recovery.backup_runs (
                    policy_id,
                    trigger,
                    status,
                    started_at
                )
                VALUES (%s, %s, %s, %s)
                RETURNING
                    run_id,
                    policy_id,
                    trigger,
                    status,
                    started_at,
                    completed_at,
                    artifact_uri,
                    artifact_size_bytes,
                    checksum_sha256,
                    error,
                    verification_status,
                    last_verified_at
                """,
                (
                    run.policy_id,
                    run.trigger,
                    run.status.value,
                    run.started_at,
                ),
            ).fetchone()

        return self._run_from_row(row)

    def update_run(self, run: BackupRun) -> None:
        if run.run_id is None:
            raise BackupRepositoryError("run has no run_id")

        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE backup_recovery.backup_runs
                SET
                    status = %s,
                    completed_at = %s,
                    artifact_uri = %s,
                    artifact_size_bytes = %s,
                    checksum_sha256 = %s,
                    error = %s,
                    verification_status = %s,
                    last_verified_at = %s
                WHERE run_id = %s
                """,
                (
                    run.status.value,
                    run.completed_at,
                    run.artifact_uri,
                    run.artifact_size_bytes,
                    run.checksum_sha256,
                    run.error,
                    run.verification_status,
                    run.last_verified_at,
                    run.run_id,
                ),
            )

    def get_run(self, run_id: UUID) -> BackupRun | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    run_id,
                    policy_id,
                    trigger,
                    status,
                    started_at,
                    completed_at,
                    artifact_uri,
                    artifact_size_bytes,
                    checksum_sha256,
                    error,
                    verification_status,
                    last_verified_at
                FROM backup_recovery.backup_runs
                WHERE run_id = %s
                """,
                (run_id,),
            ).fetchone()

        if row is None:
            return None

        return self._run_from_row(row)

    def list_runs(self, policy_id: UUID | None = None, limit: int = 100) -> list[BackupRun]:
        with self._pool.connection() as conn:
            if policy_id is None:
                rows = conn.execute(
                    """
                    SELECT
                        run_id,
                        policy_id,
                        trigger,
                        status,
                        started_at,
                        completed_at,
                        artifact_uri,
                        artifact_size_bytes,
                        checksum_sha256,
                        error,
                        verification_status,
                        last_verified_at
                    FROM backup_recovery.backup_runs
                    ORDER BY started_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT
                        run_id,
                        policy_id,
                        trigger,
                        status,
                        started_at,
                        completed_at,
                        artifact_uri,
                        artifact_size_bytes,
                        checksum_sha256,
                        error,
                        verification_status,
                        last_verified_at
                    FROM backup_recovery.backup_runs
                    WHERE policy_id = %s
                    ORDER BY started_at DESC
                    LIMIT %s
                    """,
                    (policy_id, limit),
                ).fetchall()

        return [self._run_from_row(row) for row in rows]

    def create_artifact(self, artifact: BackupArtifact) -> BackupArtifact:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO backup_recovery.backup_artifacts (
                    run_id,
                    policy_id,
                    target_system,
                    target_name,
                    storage_key,
                    uri,
                    size_bytes,
                    checksum_sha256,
                    encryption_key_ref,
                    status,
                    expires_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING
                    artifact_id,
                    run_id,
                    policy_id,
                    target_system,
                    target_name,
                    storage_key,
                    uri,
                    size_bytes,
                    checksum_sha256,
                    encryption_key_ref,
                    status,
                    created_at,
                    expires_at
                """,
                (
                    artifact.run_id,
                    artifact.policy_id,
                    artifact.target_system.value,
                    artifact.target_name,
                    artifact.storage_key,
                    artifact.uri,
                    artifact.size_bytes,
                    artifact.checksum_sha256,
                    artifact.encryption_key_ref,
                    artifact.status.value,
                    artifact.expires_at,
                ),
            ).fetchone()

        return self._artifact_from_row(row)

    def list_artifacts(self, policy_id: UUID) -> list[BackupArtifact]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    artifact_id,
                    run_id,
                    policy_id,
                    target_system,
                    target_name,
                    storage_key,
                    uri,
                    size_bytes,
                    checksum_sha256,
                    encryption_key_ref,
                    status,
                    created_at,
                    expires_at
                FROM backup_recovery.backup_artifacts
                WHERE policy_id = %s
                ORDER BY created_at DESC
                """,
                (policy_id,),
            ).fetchall()

        return [self._artifact_from_row(row) for row in rows]

    def get_artifact_by_run(self, run_id: UUID) -> BackupArtifact | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    artifact_id,
                    run_id,
                    policy_id,
                    target_system,
                    target_name,
                    storage_key,
                    uri,
                    size_bytes,
                    checksum_sha256,
                    encryption_key_ref,
                    status,
                    created_at,
                    expires_at
                FROM backup_recovery.backup_artifacts
                WHERE run_id = %s
                """,
                (run_id,),
            ).fetchone()

        if row is None:
            return None

        return self._artifact_from_row(row)

    def update_artifact_status(self, artifact_id: UUID, status: ArtifactStatus) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE backup_recovery.backup_artifacts
                SET status = %s
                WHERE artifact_id = %s
                """,
                (status.value, artifact_id),
            )

    def create_restore(self, restore: RestoreRun) -> RestoreRun:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO backup_recovery.restore_runs (
                    backup_run_id,
                    target_connection_ref,
                    target_connection_redacted,
                    command_redacted,
                    status,
                    dry_run,
                    started_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING
                    restore_id,
                    backup_run_id,
                    target_connection_ref,
                    target_connection_redacted,
                    command_redacted,
                    status,
                    dry_run,
                    started_at,
                    completed_at,
                    error
                """,
                (
                    restore.backup_run_id,
                    restore.target_connection_ref,
                    restore.target_connection_redacted,
                    restore.command_redacted,
                    restore.status.value,
                    restore.dry_run,
                    restore.started_at,
                ),
            ).fetchone()

        return self._restore_from_row(row)

    def update_restore(self, restore: RestoreRun) -> None:
        if restore.restore_id is None:
            raise BackupRepositoryError("restore has no restore_id")

        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE backup_recovery.restore_runs
                SET
                    status = %s,
                    completed_at = %s,
                    error = %s,
                    command_redacted = %s
                WHERE restore_id = %s
                """,
                (
                    restore.status.value,
                    restore.completed_at,
                    restore.error,
                    restore.command_redacted,
                    restore.restore_id,
                ),
            )