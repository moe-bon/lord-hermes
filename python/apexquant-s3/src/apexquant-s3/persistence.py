from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Protocol, Sequence

from apexquant_s3.models import BucketSpec


class DatabaseConnection(Protocol):
    def execute(self, query: str, parameters: Sequence[Any] | None = None, /) -> Any: ...
    def commit(self) -> None: ...


def persist_buckets(connection: DatabaseConnection, specs: list[BucketSpec]) -> None:
    for spec in specs:
        connection.execute(
            """
            INSERT INTO object_storage.buckets (
                bucket_name, environment, purpose, versioning_enabled, lifecycle_rules
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (bucket_name) DO UPDATE SET
                versioning_enabled = EXCLUDED.versioning_enabled,
                lifecycle_rules = EXCLUDED.lifecycle_rules,
                updated_at = now()
            """,
            (
                spec.name,
                spec.name.split("-", 1)[0],
                spec.purpose.value,
                spec.versioning_enabled,
                json.dumps(
                    [{"expiration_days": spec.lifecycle_expiration_days}]
                    if spec.lifecycle_expiration_days
                    else []
                ),
            ),
        )
    connection.commit()


def persist_verification_report(
    connection: DatabaseConnection,
    environment: str,
    endpoint: str,
    ok: bool,
    missing_buckets: list[str],
    observed_buckets: list[str],
) -> None:
    connection.execute(
        """
        INSERT INTO object_storage.verification_runs (
            environment, endpoint, generated_at, ok, missing_buckets, observed_buckets
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            environment,
            endpoint,
            datetime.now(timezone.utc),
            ok,
            json.dumps(missing_buckets),
            json.dumps(observed_buckets),
        ),
    )
    connection.commit()