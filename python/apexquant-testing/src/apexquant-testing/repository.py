from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg.types.json import Json

from apexquant_testing.models import TestRunReport


class TestingRepositoryError(Exception):
    pass


def apply_migrations(database_url: str, migrations_dir: str) -> None:
    path = Path(migrations_dir)

    if not path.exists():
        raise TestingRepositoryError(f"migrations directory does not exist: {path}")

    migrations = sorted(path.glob("*.sql"))

    if not migrations:
        raise TestingRepositoryError(f"no SQL migrations found in {path}")

    with psycopg.connect(database_url, autocommit=True) as conn:
        for migration in migrations:
            conn.execute(migration.read_text(encoding="utf-8"))


class TestingRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def persist_report(self, report: TestRunReport) -> str:
        with psycopg.connect(self._database_url) as conn:
            with conn.transaction():
                cursor = conn.execute(
                    """
                    INSERT INTO testing.test_runs (
                        environment,
                        git_sha,
                        trigger,
                        started_at,
                        completed_at,
                        ok,
                        total,
                        passed,
                        failed,
                        skipped,
                        errors,
                        coverage_pct,
                        metadata
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    RETURNING run_id
                    """,
                    (
                        report.environment,
                        report.git_sha,
                        report.trigger,
                        report.started_at,
                        report.completed_at,
                        report.ok,
                        report.total,
                        report.passed,
                        report.failed,
                        report.skipped,
                        report.errors,
                        report.coverage_pct,
                        Json({}),
                    ),
                )

                row = cursor.fetchone()

                if row is None:
                    raise TestingRepositoryError("failed to persist test run")

                run_id = str(row[0])

                if report.results:
                    conn.executemany(
                        """
                        INSERT INTO testing.test_results (
                            run_id,
                            suite,
                            name,
                            status,
                            duration_ms,
                            message,
                            details,
                            failure_mode
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
                        """,
                        [
                            (
                                run_id,
                                result.suite,
                                result.name,
                                result.status.value,
                                result.duration_ms,
                                result.message,
                                Json(result.details),
                                result.failure_mode,
                            )
                            for result in report.results
                        ],
                    )

                return run_id