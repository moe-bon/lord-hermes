from __future__ import annotations

from pathlib import Path

from psycopg_pool import ConnectionPool

from apexquant_backup_recovery.repository import (
    InMemoryBackupRepository,
    PostgresBackupRepository,
    apply_migrations,
)
from apexquant_backup_recovery.runner import SubprocessRunner
from apexquant_backup_recovery.service import BackupService
from apexquant_backup_recovery.settings import BackupSettings
from apexquant_backup_recovery.storage import LocalDirectoryStorage, S3Storage


def build_storage(settings: BackupSettings):
    if settings.storage_driver == "s3":
        return S3Storage(
            bucket=settings.default_bucket,
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            server_side_encryption=settings.s3_server_side_encryption,
        )

    return LocalDirectoryStorage(
        root=Path(settings.backup_storage_root),
        bucket=settings.default_bucket,
    )


def build_service(settings: BackupSettings) -> BackupService:
    if settings.database_url:
        if settings.migrate_on_start:
            apply_migrations(settings.database_url, settings.migrations_dir)

        pool = ConnectionPool(
            conninfo=settings.database_url,
            max_size=5,
        )

        repository = PostgresBackupRepository(pool)
    else:
        repository = InMemoryBackupRepository()

    storage = build_storage(settings)
    runner = SubprocessRunner()

    return BackupService(
        repository=repository,
        storage=storage,
        runner=runner,
        environment=settings.environment,
        workdir=Path(settings.backup_workdir),
    )