from datetime import datetime, timezone

from apexquant_migrations.models import AppliedMigration, MigrationEngine, MigrationFile
from apexquant_migrations.planner import build_plan


def make_file(migration_id: str, checksum: str) -> MigrationFile:
    return MigrationFile(
        engine=MigrationEngine.POSTGRES,
        domain="auth",
        filename=migration_id.split("/")[-1],
        path=f"/tmp/{migration_id}",
        version="0001",
        migration_id=migration_id,
        checksum_sha256=checksum,
    )


def make_applied(migration_id: str, checksum: str) -> AppliedMigration:
    return AppliedMigration(
        migration_id=migration_id,
        engine=MigrationEngine.POSTGRES,
        domain="auth",
        version="0001",
        filename=migration_id.split("/")[-1],
        checksum_sha256=checksum,
        applied_at=datetime.now(timezone.utc),
    )


def test_pending_migration_is_detected() -> None:
    file = make_file("postgres/auth/0001_init.sql", "a" * 64)

    plan = build_plan(MigrationEngine.POSTGRES, [file], {})

    assert plan.ok is True
    assert len(plan.pending) == 1
    assert plan.pending[0].migration_id == "postgres/auth/0001_init.sql"


def test_applied_migration_with_matching_checksum_is_not_pending() -> None:
    file = make_file("postgres/auth/0001_init.sql", "a" * 64)
    applied = make_applied("postgres/auth/0001_init.sql", "a" * 64)

    plan = build_plan(MigrationEngine.POSTGRES, [file], {applied.migration_id: applied})

    assert plan.ok is True
    assert len(plan.pending) == 0
    assert len(plan.drift) == 0


def test_checksum_drift_is_detected() -> None:
    file = make_file("postgres/auth/0001_init.sql", "a" * 64)
    applied = make_applied("postgres/auth/0001_init.sql", "b" * 64)

    plan = build_plan(MigrationEngine.POSTGRES, [file], {applied.migration_id: applied})

    assert plan.ok is False
    assert len(plan.pending) == 0
    assert len(plan.drift) == 1