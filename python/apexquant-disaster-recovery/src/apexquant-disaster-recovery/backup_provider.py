from __future__ import annotations

from typing import Protocol

from apexquant_disaster_recovery.models import BackupStatus


class BackupStatusProvider(Protocol):
    def policy_exists(self, policy_name: str) -> bool:
        raise NotImplementedError

    def latest_backup(self, policy_name: str) -> BackupStatus | None:
        raise NotImplementedError


class InMemoryBackupStatusProvider:
    def __init__(self) -> None:
        self._policies: set[str] = set()
        self._backups: dict[str, BackupStatus] = {}

    def add_policy(self, policy_name: str) -> None:
        self._policies.add(policy_name)

    def set_latest_backup(self, status: BackupStatus) -> None:
        self._policies.add(status.policy_name)
        self._backups[status.policy_name] = status

    def policy_exists(self, policy_name: str) -> bool:
        return policy_name in self._policies

    def latest_backup(self, policy_name: str) -> BackupStatus | None:
        return self._backups.get(policy_name)


class PostgresBackupStatusProvider:
    def __init__(self, pool) -> None:
        self._pool = pool

    def policy_exists(self, policy_name: str) -> bool:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM backup_recovery.backup_policies
                WHERE name = %s
                """,
                (policy_name,),
            ).fetchone()

        return row is not None

    def latest_backup(self, policy_name: str) -> BackupStatus | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    r.started_at,
                    r.artifact_uri,
                    r.verification_status,
                    r.last_verified_at
                FROM backup_recovery.backup_runs r
                JOIN backup_recovery.backup_policies p
                  ON p.policy_id = r.policy_id
                WHERE p.name = %s
                  AND r.status = 'SUCCEEDED'
                ORDER BY r.started_at DESC
                LIMIT 1
                """,
                (policy_name,),
            ).fetchone()

        if row is None:
            return None

        return BackupStatus(
            policy_name=policy_name,
            latest_success_at=row[0],
            latest_artifact_uri=row[1],
            verification_status=row[2],
            last_verified_at=row[3],
        )