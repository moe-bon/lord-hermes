from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from apexquant_migrations.discovery import discover_migrations
from apexquant_migrations.models import (
    AppliedMigration,
    MigrationEngine,
    MigrationRunReport,
)
from apexquant_migrations.planner import build_plan

BOOTSTRAP_SQL = """
CREATE SCHEMA IF NOT EXISTS schema_migrations;

CREATE TABLE IF NOT EXISTS schema_migrations.applied_migrations (
    migration_id      TEXT PRIMARY KEY,
    engine            TEXT NOT NULL,
    domain            TEXT NOT NULL,
    version           TEXT NOT NULL,
    filename          TEXT NOT NULL,
    checksum_sha256   CHAR(64) NOT NULL,
    applied_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_by        TEXT NOT NULL DEFAULT 'unknown',
    execution_time_ms INTEGER,

    CONSTRAINT applied_migrations_engine_valid
        CHECK (engine IN ('postgres', 'clickhouse')),

    CONSTRAINT applied_migrations_domain_not_empty
        CHECK (length(trim(domain)) > 0),

    CONSTRAINT applied_migrations_version_not_empty
        CHECK (length(trim(version)) > 0),

    CONSTRAINT applied_migrations_filename_not_empty
        CHECK (length(trim(filename)) > 0),

    CONSTRAINT applied_migrations_checksum_format
        CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS schema_migrations_applied_engine_idx
    ON schema_migrations.applied_migrations (engine);

CREATE INDEX IF NOT EXISTS schema_migrations_applied_domain_idx
    ON schema_migrations.applied_migrations (domain);

CREATE INDEX IF NOT EXISTS schema_migrations_applied_applied_at_idx
    ON schema_migrations.applied_migrations (applied_at DESC);

CREATE TABLE IF NOT EXISTS schema_migrations.migration_runs (
    run_id         UUID PRIMARY KEY,
    engine         TEXT NOT NULL,
    mode           TEXT NOT NULL,
    status         TEXT NOT NULL,
    planned_count  INTEGER NOT NULL DEFAULT 0,
    applied_count  INTEGER NOT NULL DEFAULT 0,
    skipped_count  INTEGER NOT NULL DEFAULT 0,
    failed_count   INTEGER NOT NULL DEFAULT 0,
    error          TEXT,
    started_at     TIMESTAMPTZ NOT NULL,
    completed_at   TIMESTAMPTZ,
    metadata       JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT migration_runs_engine_valid
        CHECK (engine IN ('postgres', 'clickhouse')),

    CONSTRAINT migration_runs_status_valid
        CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),

    CONSTRAINT migration_runs_mode_valid
        CHECK (mode IN ('apply', 'baseline', 'verify', 'dry-run'))
);

CREATE INDEX IF NOT EXISTS schema_migrations_runs_started_at_idx
    ON schema_migrations.migration_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS schema_migrations_runs_status_idx
    ON schema_migrations.migration_runs (status);

CREATE TABLE IF NOT EXISTS schema_migrations.migration_locks (
    lock_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engine       TEXT NOT NULL,
    acquired_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    acquired_by  TEXT NOT NULL,
    expires_at   TIMESTAMPTZ,
    released_at  TIMESTAMPTZ,

    CONSTRAINT migration_locks_engine_valid
        CHECK (engine IN ('postgres', 'clickhouse')),

    CONSTRAINT migration_locks_acquired_by_not_empty
        CHECK (length(trim(acquired_by)) > 0)
);

CREATE INDEX IF NOT EXISTS schema_migrations_locks_engine_idx
    ON schema_migrations.migration_locks (engine, acquired_at DESC);
"""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PostgresMigrationError(Exception):
    pass


class PostgresMigrator:
    def __init__(
        self,
        database_url: str,
        migrations_root: Path | str,
        applied_by: str = "apexquant-migrate",
    ) -> None:
        self._database_url = database_url
        self._migrations_root = Path(migrations_root)
        self._applied_by = applied_by

    def _connect(self):
        conn = psycopg.connect(self._database_url)
        conn.autocommit = True
        return conn

    def ensure_registry(self, conn) -> None:
        conn.execute(BOOTSTRAP_SQL)

    def acquire_lock(self, conn) -> None:
        conn.execute("SELECT pg_advisory_lock(hashtext('apexquant_migrations'))")

    def release_lock(self, conn) -> None:
        conn.execute("SELECT pg_advisory_unlock(hashtext('apexquant_migrations'))")

    def get_applied(self, conn) -> dict[str, AppliedMigration]:
        rows = conn.execute(
            """
            SELECT
                migration_id,
                engine,
                domain,
                version,
                filename,
                checksum_sha256,
                applied_at
            FROM schema_migrations.applied_migrations
            WHERE engine = 'postgres'
            ORDER BY domain, version, filename
            """
        ).fetchall()

        applied: dict[str, AppliedMigration] = {}

        for row in rows:
            migration = AppliedMigration(
                migration_id=row[0],
                engine=MigrationEngine(row[1]),
                domain=row[2],
                version=row[3],
                filename=row[4],
                checksum_sha256=row[5].strip(),
                applied_at=row[6],
            )

            applied[migration.migration_id] = migration

        return applied

    def plan(self, domain: str | None = None):
        files = discover_migrations(
            self._migrations_root,
            MigrationEngine.POSTGRES,
            domain_filter=domain,
        )

        with self._connect() as conn:
            self.ensure_registry(conn)
            applied = self.get_applied(conn)

        return build_plan(MigrationEngine.POSTGRES, files, applied)

    def verify(self, domain: str | None = None) -> MigrationRunReport:
        started_at = utc_now()

        migration_plan = self.plan(domain)

        completed_at = utc_now()

        ok = migration_plan.ok and len(migration_plan.pending) == 0

        details: list[dict] = []

        if migration_plan.drift:
            details.append(
                {
                    "type": "drift",
                    "items": migration_plan.drift,
                }
            )

        if migration_plan.pending:
            details.append(
                {
                    "type": "pending",
                    "items": [file.migration_id for file in migration_plan.pending],
                }
            )

        return MigrationRunReport(
            engine=MigrationEngine.POSTGRES,
            mode="verify",
            started_at=started_at,
            completed_at=completed_at,
            ok=ok,
            planned=len(migration_plan.pending),
            applied=0,
            skipped=len(migration_plan.pending),
            failed=len(migration_plan.drift),
            details=details,
        )

    def apply(
        self,
        domain: str | None = None,
        dry_run: bool = False,
    ) -> MigrationRunReport:
        started_at = utc_now()

        migration_plan = self.plan(domain)

        if not migration_plan.ok:
            raise PostgresMigrationError(
                f"migration checksum drift detected: {migration_plan.drift}"
            )

        if dry_run:
            return MigrationRunReport(
                engine=MigrationEngine.POSTGRES,
                mode="dry-run",
                started_at=started_at,
                completed_at=utc_now(),
                ok=True,
                planned=len(migration_plan.pending),
                applied=0,
                skipped=len(migration_plan.pending),
                failed=0,
                details=[
                    {"type": "pending", "migration_id": file.migration_id}
                    for file in migration_plan.pending
                ],
            )

        applied_count = 0
        details: list[dict] = []

        with self._connect() as conn:
            self.ensure_registry(conn)
            self.acquire_lock(conn)

            run_id = uuid.uuid4()

            conn.execute(
                """
                INSERT INTO schema_migrations.migration_runs (
                    run_id,
                    engine,
                    mode,
                    status,
                    planned_count,
                    started_at
                )
                VALUES (
                    %s,
                    'postgres',
                    'apply',
                    'RUNNING',
                    %s,
                    now()
                )
                """,
                (run_id, len(migration_plan.pending)),
            )

            try:
                for file in migration_plan.pending:
                    file_started = utc_now()

                    sql = Path(file.path).read_text(encoding="utf-8")

                    conn.execute(sql)

                    elapsed_ms = int((utc_now() - file_started).total_seconds() * 1000)

                    conn.execute(
                        """
                        INSERT INTO schema_migrations.applied_migrations (
                            migration_id,
                            engine,
                            domain,
                            version,
                            filename,
                            checksum_sha256,
                            applied_by,
                            execution_time_ms
                        )
                        VALUES (
                            %s,
                            'postgres',
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s
                        )
                        ON CONFLICT (migration_id) DO NOTHING
                        """,
                        (
                            file.migration_id,
                            file.domain,
                            file.version,
                            file.filename,
                            file.checksum_sha256,
                            self._applied_by,
                            elapsed_ms,
                        ),
                    )

                    applied_count += 1

                    details.append(
                        {
                            "type": "applied",
                            "migration_id": file.migration_id,
                            "execution_time_ms": elapsed_ms,
                        }
                    )

                conn.execute(
                    """
                    UPDATE schema_migrations.migration_runs
                    SET
                        status = 'SUCCESS',
                        applied_count = %s,
                        completed_at = now()
                    WHERE run_id = %s
                    """,
                    (applied_count, run_id),
                )

                self.release_lock(conn)

                return MigrationRunReport(
                    engine=MigrationEngine.POSTGRES,
                    mode="apply",
                    started_at=started_at,
                    completed_at=utc_now(),
                    ok=True,
                    planned=len(migration_plan.pending),
                    applied=applied_count,
                    skipped=0,
                    failed=0,
                    details=details,
                )
            except Exception as exc:
                conn.execute(
                    """
                    UPDATE schema_migrations.migration_runs
                    SET
                        status = 'FAILED',
                        applied_count = %s,
                        failed_count = 1,
                        error = %s,
                        completed_at = now()
                    WHERE run_id = %s
                    """,
                    (applied_count, str(exc), run_id),
                )

                self.release_lock(conn)

                raise PostgresMigrationError(str(exc)) from exc

    def baseline(
        self,
        domain: str | None = None,
        confirm: bool = False,
    ) -> MigrationRunReport:
        if not confirm:
            raise PostgresMigrationError(
                "baseline must be explicitly confirmed with --confirm-baseline"
            )

        started_at = utc_now()

        migration_plan = self.plan(domain)

        applied_count = 0
        details: list[dict] = []

        with self._connect() as conn:
            self.ensure_registry(conn)
            self.acquire_lock(conn)

            try:
                for file in migration_plan.pending:
                    conn.execute(
                        """
                        INSERT INTO schema_migrations.applied_migrations (
                            migration_id,
                            engine,
                            domain,
                            version,
                            filename,
                            checksum_sha256,
                            applied_by,
                            execution_time_ms
                        )
                        VALUES (
                            %s,
                            'postgres',
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            0
                        )
                        ON CONFLICT (migration_id) DO NOTHING
                        """,
                        (
                            file.migration_id,
                            file.domain,
                            file.version,
                            file.filename,
                            file.checksum_sha256,
                            self._applied_by,
                        ),
                    )

                    applied_count += 1

                    details.append(
                        {
                            "type": "baselined",
                            "migration_id": file.migration_id,
                        }
                    )

                self.release_lock(conn)

                return MigrationRunReport(
                    engine=MigrationEngine.POSTGRES,
                    mode="baseline",
                    started_at=started_at,
                    completed_at=utc_now(),
                    ok=True,
                    planned=len(migration_plan.pending),
                    applied=applied_count,
                    skipped=0,
                    failed=0,
                    details=details,
                )
            except Exception as exc:
                self.release_lock(conn)
                raise PostgresMigrationError(str(exc)) from exc