from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg_pool import ConnectionPool

from apexquant_audit.hashing import (
    GENESIS_HASH,
    AuditFields,
    compute_event_hash,
)
from apexquant_audit.models import AuditEventRecord


class AuditRepositoryError(Exception):
    pass


EVENT_COLUMNS = [
    "event_seq",
    "event_id",
    "occurred_at",
    "received_at",
    "actor_type",
    "actor_id",
    "principal_name",
    "service_name",
    "plane",
    "action",
    "resource_type",
    "resource_id",
    "decision",
    "reason",
    "severity",
    "request_id",
    "correlation_id",
    "trace_id",
    "idempotency_key",
    "data",
    "prev_hash",
    "event_hash",
]


def apply_migrations(database_url: str, migrations_dir: str) -> None:
    path = Path(migrations_dir)

    if not path.exists():
        raise AuditRepositoryError(f"migrations directory does not exist: {path}")

    migrations = sorted(path.glob("*.sql"))

    if not migrations:
        raise AuditRepositoryError(f"no SQL migrations found in {path}")

    with psycopg.connect(database_url, autocommit=True) as conn:
        for migration in migrations:
            conn.execute(migration.read_text(encoding="utf-8"))


class PostgresAuditRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def append_event(self, fields: AuditFields) -> AuditEventRecord:
        with self._pool.connection() as conn:
            with conn.transaction():
                conn.execute("SELECT pg_advisory_xact_lock(hashtext('audit_chain'))")

                row = conn.execute(
                    """
                    SELECT event_hash
                    FROM audit.events
                    ORDER BY event_seq DESC
                    LIMIT 1
                    """
                ).fetchone()

                prev_hash = row[0] if row else GENESIS_HASH
                event_hash = compute_event_hash(fields, prev_hash)

                cursor = conn.execute(
                    """
                    INSERT INTO audit.events (
                        event_id,
                        occurred_at,
                        actor_type,
                        actor_id,
                        principal_name,
                        service_name,
                        plane,
                        action,
                        resource_type,
                        resource_id,
                        decision,
                        reason,
                        severity,
                        request_id,
                        correlation_id,
                        trace_id,
                        idempotency_key,
                        data,
                        prev_hash,
                        event_hash
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (event_id) DO NOTHING
                    RETURNING event_seq, event_id, occurred_at, event_hash
                    """,
                    (
                        fields.event_id,
                        fields.occurred_at,
                        fields.actor_type,
                        fields.actor_id,
                        fields.principal_name,
                        fields.service_name,
                        fields.plane,
                        fields.action,
                        fields.resource_type,
                        fields.resource_id,
                        fields.decision,
                        fields.reason,
                        fields.severity,
                        fields.request_id,
                        fields.correlation_id,
                        fields.trace_id,
                        fields.idempotency_key,
                        psycopg.types.json.Json(fields.data),
                        prev_hash,
                        event_hash,
                    ),
                )

                inserted = cursor.fetchone()

                if inserted:
                    return AuditEventRecord(
                        event_seq=inserted[0],
                        event_id=inserted[1],
                        occurred_at=inserted[2],
                        event_hash=inserted[3],
                    )

                existing = conn.execute(
                    """
                    SELECT event_seq, event_id, occurred_at, event_hash
                    FROM audit.events
                    WHERE event_id = %s
                    """,
                    (fields.event_id,),
                ).fetchone()

                if existing is None:
                    raise AuditRepositoryError("audit append failed")

                return AuditEventRecord(
                    event_seq=existing[0],
                    event_id=existing[1],
                    occurred_at=existing[2],
                    event_hash=existing[3],
                )

    def fetch_events(
        self,
        limit: int = 100,
        service_name: str | None = None,
        action: str | None = None,
        request_id: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = f"SELECT {', '.join(EVENT_COLUMNS)} FROM audit.events WHERE TRUE"
        params: list[Any] = []

        if service_name:
            sql += " AND service_name = %s"
            params.append(service_name)

        if action:
            sql += " AND action = %s"
            params.append(action)

        if request_id:
            sql += " AND request_id = %s"
            params.append(request_id)

        sql += " ORDER BY event_seq DESC LIMIT %s"
        params.append(max(1, min(limit, 1000)))

        with self._pool.connection() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [dict(zip(EVENT_COLUMNS, row)) for row in rows]

    def fetch_verification_range(
        self,
        start_seq: int | None = None,
        end_seq: int | None = None,
        limit: int = 1000,
    ) -> tuple[str, list[dict[str, Any]]]:
        with self._pool.connection() as conn:
            if start_seq is None or start_seq <= 1:
                initial_prev_hash = GENESIS_HASH
                start = 1
            else:
                row = conn.execute(
                    """
                    SELECT event_hash
                    FROM audit.events
                    WHERE event_seq = %s
                    """,
                    (start_seq - 1,),
                ).fetchone()

                if row is None:
                    raise AuditRepositoryError(
                        f"cannot verify from sequence {start_seq}: previous event missing"
                    )

                initial_prev_hash = row[0]
                start = start_seq

            sql = f"""
                SELECT {', '.join(EVENT_COLUMNS)}
                FROM audit.events
                WHERE event_seq >= %s
            """
            params: list[Any] = [start]

            if end_seq is not None:
                sql += " AND event_seq <= %s"
                params.append(end_seq)

            sql += " ORDER BY event_seq ASC LIMIT %s"
            params.append(max(1, min(limit, 10000)))

            rows = conn.execute(sql, params).fetchall()

        return initial_prev_hash, [dict(zip(EVENT_COLUMNS, row)) for row in rows]

    def fetch_unpublished(self, limit: int = 100) -> list[dict[str, Any]]:
        sql = f"""
            SELECT {', '.join(f'e.{column}' for column in EVENT_COLUMNS)}
            FROM audit.events e
            LEFT JOIN audit.event_delivery d ON d.event_seq = e.event_seq
            WHERE d.published_at IS NULL
            ORDER BY e.event_seq ASC
            LIMIT %s
        """

        with self._pool.connection() as conn:
            rows = conn.execute(sql, (max(1, min(limit, 1000)),)).fetchall()

        return [dict(zip(EVENT_COLUMNS, row)) for row in rows]

    def record_delivery(
        self,
        event_seq: int,
        success: bool,
        error: str | None,
    ) -> None:
        with self._pool.connection() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO audit.event_delivery (
                        event_seq,
                        published_at,
                        attempts,
                        last_error
                    )
                    VALUES (
                        %s,
                        CASE WHEN %s THEN now() ELSE NULL END,
                        1,
                        %s
                    )
                    ON CONFLICT (event_seq) DO UPDATE SET
                        published_at = CASE
                            WHEN %s THEN now()
                            ELSE audit.event_delivery.published_at
                        END,
                        attempts = audit.event_delivery.attempts + 1,
                        last_error = EXCLUDED.last_error,
                        updated_at = now()
                    """,
                    (
                        event_seq,
                        success,
                        error,
                        success,
                    ),
                )

    def record_integrity_check(
        self,
        start_seq: int | None,
        end_seq: int | None,
        report: dict[str, Any],
    ) -> None:
        with self._pool.connection() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO audit.integrity_checks (
                        start_seq,
                        end_seq,
                        events_checked,
                        ok,
                        violations,
                        completed_at
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        now()
                    )
                    """,
                    (
                        start_seq,
                        end_seq,
                        report.get("events_checked", 0),
                        report.get("ok", False),
                        psycopg.types.json.Json(report.get("violations", [])),
                    ),
                )