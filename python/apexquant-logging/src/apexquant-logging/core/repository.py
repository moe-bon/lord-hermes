from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

from apexquant_logging.core.settings import LoggingCoreSettings


class LoggingRepositoryError(Exception):
    pass


def apply_migrations(database_url: str, migrations_dir: str) -> None:
    path = Path(migrations_dir)

    if not path.exists():
        raise LoggingRepositoryError(f"migrations directory does not exist: {path}")

    migrations = sorted(path.glob("*.sql"))

    if not migrations:
        raise LoggingRepositoryError(f"no SQL migrations found in {path}")

    with psycopg.connect(database_url, autocommit=True) as conn:
        for migration in migrations:
            conn.execute(migration.read_text(encoding="utf-8"))


class LoggingConfigRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def get_service_configs(self) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    service_name,
                    environment,
                    plane,
                    default_level,
                    json_output,
                    redaction_enabled
                FROM logging.service_log_configs
                ORDER BY service_name
                """
            ).fetchall()

        return [
            {
                "service_name": row[0],
                "environment": row[1],
                "plane": row[2],
                "default_level": row[3],
                "json_output": row[4],
                "redaction_enabled": row[5],
            }
            for row in rows
        ]

    def upsert_service_config(
        self,
        service_name: str,
        environment: str,
        plane: str,
        default_level: str,
        json_output: bool,
        redaction_enabled: bool,
    ) -> None:
        with self._pool.connection() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO logging.service_log_configs (
                        service_name,
                        environment,
                        plane,
                        default_level,
                        json_output,
                        redaction_enabled
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    ON CONFLICT (service_name) DO UPDATE SET
                        environment = EXCLUDED.environment,
                        plane = EXCLUDED.plane,
                        default_level = EXCLUDED.default_level,
                        json_output = EXCLUDED.json_output,
                        redaction_enabled = EXCLUDED.redaction_enabled,
                        updated_at = now()
                    """,
                    (
                        service_name,
                        environment,
                        plane,
                        default_level,
                        json_output,
                        redaction_enabled,
                    ),
                )