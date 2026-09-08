from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

from apexquant_tracing.core.settings import TracingCoreSettings


class TracingRepositoryError(Exception):
    pass


def apply_migrations(database_url: str, migrations_dir: str) -> None:
    path = Path(migrations_dir)

    if not path.exists():
        raise TracingRepositoryError(f"migrations directory does not exist: {path}")

    migrations = sorted(path.glob("*.sql"))

    if not migrations:
        raise TracingRepositoryError(f"no SQL migrations found in {path}")

    with psycopg.connect(database_url, autocommit=True) as conn:
        for migration in migrations:
            conn.execute(migration.read_text(encoding="utf-8"))


class TracingConfigRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def get_config(self, service_name: str) -> dict | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    service_name,
                    environment,
                    plane,
                    otlp_endpoint,
                    tempo_query_endpoint,
                    sample_ratio,
                    tracing_enabled,
                    redaction_enabled
                FROM tracing.service_tracing_configs
                WHERE service_name = %s
                """,
                (service_name,),
            ).fetchone()

        if row is None:
            return None

        return {
            "service_name": row[0],
            "environment": row[1],
            "plane": row[2],
            "otlp_endpoint": row[3],
            "tempo_query_endpoint": row[4],
            "sample_ratio": float(row[5]),
            "tracing_enabled": row[6],
            "redaction_enabled": row[7],
        }

    def upsert_config(
        self,
        service_name: str,
        environment: str,
        plane: str,
        otlp_endpoint: str | None,
        tempo_query_endpoint: str | None,
        sample_ratio: float,
        tracing_enabled: bool,
        redaction_enabled: bool,
    ) -> None:
        with self._pool.connection() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO tracing.service_tracing_configs (
                        service_name,
                        environment,
                        plane,
                        otlp_endpoint,
                        tempo_query_endpoint,
                        sample_ratio,
                        tracing_enabled,
                        redaction_enabled
                    )
                    VALUES (
                        %s,
                        %s,
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
                        otlp_endpoint = EXCLUDED.otlp_endpoint,
                        tempo_query_endpoint = EXCLUDED.tempo_query_endpoint,
                        sample_ratio = EXCLUDED.sample_ratio,
                        tracing_enabled = EXCLUDED.tracing_enabled,
                        redaction_enabled = EXCLUDED.redaction_enabled,
                        updated_at = now()
                    """,
                    (
                        service_name,
                        environment,
                        plane,
                        otlp_endpoint,
                        tempo_query_endpoint,
                        sample_ratio,
                        tracing_enabled,
                        redaction_enabled,
                    ),
                )