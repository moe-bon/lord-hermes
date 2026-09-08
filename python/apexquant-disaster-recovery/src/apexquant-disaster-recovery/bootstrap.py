from __future__ import annotations

from psycopg_pool import ConnectionPool

from apexquant_disaster_recovery.backup_provider import (
    InMemoryBackupStatusProvider,
    PostgresBackupStatusProvider,
)
from apexquant_disaster_recovery.health import HttpHealthChecker, NullHealthChecker
from apexquant_disaster_recovery.repository import (
    InMemoryDRRepository,
    PostgresDRRepository,
    apply_migrations,
)
from apexquant_disaster_recovery.service import DisasterRecoveryService
from apexquant_disaster_recovery.settings import DisasterRecoverySettings


def build_service(settings: DisasterRecoverySettings) -> DisasterRecoveryService:
    if settings.database_url:
        if settings.migrate_on_start:
            apply_migrations(settings.database_url, settings.migrations_dir)

        pool = ConnectionPool(
            conninfo=settings.database_url,
            max_size=5,
        )

        repository = PostgresDRRepository(pool)
        backup_provider = PostgresBackupStatusProvider(pool)
    else:
        repository = InMemoryDRRepository()
        backup_provider = InMemoryBackupStatusProvider()

    if settings.enable_health_checks:
        health_checker = HttpHealthChecker(
            timeout_seconds=settings.health_timeout_seconds
        )
    else:
        health_checker = NullHealthChecker()

    return DisasterRecoveryService(
        repository=repository,
        backup_provider=backup_provider,
        health_checker=health_checker,
        enable_health_checks=settings.enable_health_checks,
    )