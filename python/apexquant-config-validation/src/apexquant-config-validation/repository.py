from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool


class ConfigRepositoryError(Exception):
    pass


def apply_migrations(database_url: str, migrations_dir: str) -> None:
    path = Path(migrations_dir)

    if not path.exists():
        raise ConfigRepositoryError(f"migrations directory does not exist: {path}")

    migrations = sorted(path.glob("*.sql"))

    if not migrations:
        raise ConfigRepositoryError(f"no SQL migrations found in {path}")

    with psycopg.connect(database_url, autocommit=True) as conn:
        for migration in migrations:
            conn.execute(migration.read_text(encoding="utf-8"))


class ConfigRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def register_schema(
        self,
        schema_key: str,
        schema_version: str,
        json_schema: dict[str, Any],
        description: str = "",
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO config_validation.config_schemas (
                    schema_key,
                    schema_version,
                    json_schema,
                    description
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (schema_key, schema_version) DO UPDATE SET
                    json_schema = EXCLUDED.json_schema,
                    description = EXCLUDED.description,
                    updated_at = now()
                """,
                (
                    schema_key,
                    schema_version,
                    Json(json_schema),
                    description,
                ),
            )

    def list_schemas(self) -> list[dict[str, Any]]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    schema_key,
                    schema_version,
                    description,
                    created_at,
                    updated_at
                FROM config_validation.config_schemas
                ORDER BY schema_key, schema_version
                """
            ).fetchall()

        return [
            {
                "schema_key": row[0],
                "schema_version": row[1],
                "description": row[2],
                "created_at": row[3].isoformat(),
                "updated_at": row[4].isoformat(),
            }
            for row in rows
        ]

    def persist_document(
        self,
        *,
        schema_key: str,
        schema_version: str,
        service_name: str | None,
        environment: str | None,
        config_hash: str,
        values: dict[str, Any],
        created_by: str,
    ) -> str:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO config_validation.config_documents (
                    schema_key,
                    schema_version,
                    service_name,
                    environment,
                    config_hash,
                    values,
                    status,
                    created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'DRAFT', %s)
                RETURNING document_id
                """,
                (
                    schema_key,
                    schema_version,
                    service_name,
                    environment,
                    config_hash,
                    Json(values),
                    created_by,
                ),
            ).fetchone()

        if row is None:
            raise ConfigRepositoryError("failed to persist config document")

        return str(row[0])

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    document_id,
                    schema_key,
                    schema_version,
                    service_name,
                    environment,
                    config_hash,
                    values,
                    status,
                    created_by,
                    created_at,
                    updated_at
                FROM config_validation.config_documents
                WHERE document_id = %s
                """,
                (document_id,),
            ).fetchone()

        if row is None:
            return None

        return {
            "document_id": str(row[0]),
            "schema_key": row[1],
            "schema_version": row[2],
            "service_name": row[3],
            "environment": row[4],
            "config_hash": row[5],
            "values": row[6],
            "status": row[7],
            "created_by": row[8],
            "created_at": row[9].isoformat(),
            "updated_at": row[10].isoformat(),
        }

    def persist_validation_run(
        self,
        *,
        document_id: str | None,
        schema_key: str,
        environment: str | None,
        trigger: str,
        ok: bool,
        errors: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
        config_hash: str | None,
    ) -> str:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO config_validation.config_validation_runs (
                    document_id,
                    schema_key,
                    environment,
                    trigger,
                    ok,
                    errors,
                    warnings,
                    config_hash
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING run_id
                """,
                (
                    document_id,
                    schema_key,
                    environment,
                    trigger,
                    ok,
                    Json(errors),
                    Json(warnings),
                    config_hash,
                ),
            ).fetchone()

        if row is None:
            raise ConfigRepositoryError("failed to persist validation run")

        return str(row[0])

    def record_event(
        self,
        *,
        document_id: str,
        event_type: str,
        actor: str,
        reason: str,
        before_hash: str | None,
        after_hash: str | None,
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO config_validation.config_events (
                    document_id,
                    event_type,
                    actor,
                    reason,
                    before_hash,
                    after_hash
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    document_id,
                    event_type,
                    actor,
                    reason,
                    before_hash,
                    after_hash,
                ),
            )