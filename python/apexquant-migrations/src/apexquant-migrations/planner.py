from __future__ import annotations

from typing import Mapping

from apexquant_migrations.models import (
    AppliedMigration,
    MigrationEngine,
    MigrationFile,
    MigrationPlan,
)


def build_plan(
    engine: MigrationEngine,
    files: list[MigrationFile],
    applied: Mapping[str, AppliedMigration],
) -> MigrationPlan:
    pending: list[MigrationFile] = []
    drift: list[dict] = []

    for file in files:
        existing = applied.get(file.migration_id)

        if existing is None:
            pending.append(file)
            continue

        if existing.checksum_sha256 != file.checksum_sha256:
            drift.append(
                {
                    "migration_id": file.migration_id,
                    "expected_checksum": file.checksum_sha256,
                    "recorded_checksum": existing.checksum_sha256,
                }
            )

    return MigrationPlan(
        engine=engine,
        ok=len(drift) == 0,
        pending=pending,
        applied=list(applied.values()),
        drift=drift,
    )