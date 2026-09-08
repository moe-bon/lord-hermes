from __future__ import annotations

import fcntl
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import clickhouse_connect
import psycopg

from apexquant_migrations.discovery import discover_migrations
from apexquant_migrations.models import (
    AppliedMigration,
    MigrationEngine,
    MigrationRunReport,
)
from apexquant_migrations.planner import build_plan

BOOTSTRAP_STATEMENTS = [
    "CREATE DATABASE IF NOT EXISTS schema_migrations",
    """
    CREATE TABLE IF NOT EXISTS schema_migrations.applied_migrations
    (
        migration_id    String,
        engine          LowCardinality(String),
        domain          LowCardinality(String),
        version         LowCardinality(String),
        filename        String,
        checksum_sha256 FixedString(64),
        applied_at      DateTime64(3, 'UTC'),
        applied_by      String
    )
    ENGINE = ReplacingMergeTree(applied_at)
    ORDER BY migration_id
    """,
    """
    CREATE TABLE IF NOT EXISTS schema_migrations.migration_runs
    (
        run_id        UUID,
        engine        LowCardinality(String),
        mode          LowCardinality(String),
        status        LowCardinality(String),
        planned_count UInt32,
        applied_count UInt32,
        skipped_count UInt32,
        failed_count  UInt32,
        error         String,
        started_at    DateTime64(3, 'UTC'),
        completed_at  DateTime64(3, 'UTC')
    )
    ENGINE = MergeTree
    PARTITION BY toDate(started_at)
    ORDER BY (started_at, run_id)
    """,
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ClickHouseMigrationError(Exception):
    pass


def split_sql(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []

    for raw_line in sql.splitlines():
        stripped = raw_line.strip()

        if stripped.startswith("--"):
            continue

        current.append(raw_line)

        if stripped.endswith(";"):
            statement = "\n".join(current).strip().rstrip(";").strip()

            if statement:
                statements.append(statement)

            current = []

    tail = "\n".join(current).strip().rstrip(";").strip()

    if tail:
        statements.append(tail)

    return statements


class FileLock:
    def __init__(self, path: str) -> None:
        self._path = path
        self._fd: int | None = None

    def acquire(self) -> None:
        self._fd = os.open(self._path, os.O_CREAT | os.O_RDWR)
        fcntl.flock(self._fd, fcntl.LOCK_EX)

    def release(self) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None


class PostgresAdvisoryLock:
    def __init__(self, database_url: str, lock_name: str) -> None:
        self._database_url = database_url
        self._lock_name = lock_name
        self._conn = None

    def acquire(self) -> None:
        self._conn = psycopg.connect(self._database_url)
        self._conn.autocommit = True
        self._conn.execute(
            "SELECT pg_advisory_lock(hashtext(%s))",
            (self._lock_name,),
        )

    def release(self) -> None:
        if self._conn is not None:
            self._conn.execute(
                "SELECT pg_advisory_unlock(hashtext(%s))",
                (self._lock_name,),
            )
            self._conn.close()
            self._conn = None


class ClickHouseMigrator:
    def __init__(
        self,
        clickhouse_url: str,
        migrations_root: Path | str,
        postgres_url: str | None = None,
        applied_by: str = "apexquant-migrate",
        lock_path: str = "/tmp/apexquant-clickhouse-migrations.lock",
    ) -> None:
        self._clickhouse_url = clickhouse_url
        self._migrations_root = Path(migrations_root)
        self._postgres_url = postgres_url
        self._applied_by = applied_by
        self._lock_path = lock_path

    def _client(self):
        return clickhouse_connect.get_client(dsn=self._clickhouse_url)

    def _lock(self):
        if self._postgres_url:
            return PostgresAdvisoryLock(
                self._postgres_url,
                "apexquant_clickhouse_migrations",
            )

        return FileLock(self._lock_path)

    def ensure_registry(self, client) -> None:
        for statement in BOOTSTRAP_STATEMENTS:
            client.command(statement)

    def get_applied(self, client) -> dict[str, AppliedMigration]:
        result = client.query(
            """
            SELECT
                migration_id,
                engine,
                domain,
                version,
                filename,
                checksum_sha256,
                applied_at
            FROM schema_migrations.applied_migrations FINAL
            WHERE engine = 'clickhouse'
            """
        )

        applied: dict[str, AppliedMigration] = {}

        for row in result.result_rows:
            migration = AppliedMigration(
                migration_id=row[0],
                engine=MigrationEngine(row[1]),
                domain=row[2],
                version=row[3],
                filename=row[4],
                checksum_sha256=row[5],
                applied_at=row[6],
            )

            applied[migration.migration_id] = migration

        return applied

    def plan(self, domain: str | None = None):
        files = discover_migrations(
            self._migrations_root,
            MigrationEngine.CLICKHOUSE,
            domain_filter=domain,
        )

        client = self._client()

        try:
            self.ensure_registry(client)
            applied = self.get_applied(client)
        finally:
            client.close()

        return build_plan(MigrationEngine.CLICKHOUSE, files, applied)

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
            engine=MigrationEngine.CLICKHOUSE,
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
            raise ClickHouseMigrationError(
                f"migration checksum drift detected: {migration_plan.drift}"
            )

        if dry_run:
            return MigrationRunReport(
                engine=MigrationEngine.CLICKHOUSE,
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

        lock = self._lock()
        lock.acquire()

        applied_count = 0
        details: list[dict] = []

        client = self._client()

        run_id = uuid.uuid4()

        try:
            self.ensure_registry(client)

            for file in migration_plan.pending:
                sql = Path(file.path).read_text(encoding="utf-8")

                for statement in split_sql(sql):
                    client.command(statement)

                applied_at = utc_now()

                client.insert(
                    table="applied_migrations",
                    database="schema_migrations",
                    data=[
                        (
                            file.migration_id,
                            "clickhouse",
                            file.domain,
                            file.version,
                            file.filename,
                            file.checksum_sha256,
                            applied_at,
                            self._applied_by,
                        )
                    ],
                    column_names=[
                        "migration_id",
                        "engine",
                        "domain",
                        "version",
                        "filename",
                        "checksum_sha256",
                        "applied_at",
                        "applied_by",
                    ],
                )

                applied_count += 1

                details.append(
                    {
                        "type": "applied",
                        "migration_id": file.migration_id,
                    }
                )

            client.insert(
                table="migration_runs",
                database="schema_migrations",
                data=[
                    (
                        run_id,
                        "clickhouse",
                        "apply",
                        "SUCCESS",
                        len(migration_plan.pending),
                        applied_count,
                        0,
                        0,
                        "",
                        started_at,
                        utc_now(),
                    )
                ],
                column_names=[
                    "run_id",
                    "engine",
                    "mode",
                    "status",
                    "planned_count",
                    "applied_count",
                    "skipped_count",
                    "failed_count",
                    "error",
                    "started_at",
                    "completed_at",
                ],
            )

            return MigrationRunReport(
                engine=MigrationEngine.CLICKHOUSE,
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
            client.insert(
                table="migration_runs",
                database="schema_migrations",
                data=[
                    (
                        run_id,
                        "clickhouse",
                        "apply",
                        "FAILED",
                        len(migration_plan.pending),
                        applied_count,
                        0,
                        1,
                        str(exc),
                        started_at,
                        utc_now(),
                    )
                ],
                column_names=[
                    "run_id",
                    "engine",
                    "mode",
                    "status",
                    "planned_count",
                    "applied_count",
                    "skipped_count",
                    "failed_count",
                    "error",
                    "started_at",
                    "completed_at",
                ],
            )

            raise ClickHouseMigrationError(str(exc)) from exc
        finally:
            client.close()
            lock.release()