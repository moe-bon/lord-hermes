from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from apexquant_service_versioning.errors import ConflictError, NotFoundError
from apexquant_service_versioning.models import LifecycleStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryRepository:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._services: dict[str, dict[str, Any]] = {}
        self._versions: dict[str, dict[str, Any]] = {}
        self._dependencies: dict[str, list[dict[str, str]]] = {}
        self._events: list[dict[str, Any]] = []

    def upsert_service(
        self,
        service_name: str,
        plane: str,
        description: str,
    ) -> dict[str, Any]:
        with self._lock:
            now = utc_now()

            existing = self._services.get(service_name)

            if existing is None:
                record = {
                    "service_name": service_name,
                    "plane": plane,
                    "description": description,
                    "created_at": now,
                    "updated_at": now,
                }
            else:
                record = dict(existing)
                record["plane"] = plane
                record["description"] = description
                record["updated_at"] = now

            self._services[service_name] = record

            return record

    def get_service(self, service_name: str) -> dict[str, Any] | None:
        with self._lock:
            return self._services.get(service_name)

    def list_services(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(
                self._services.values(),
                key=lambda service: service["service_name"],
            )

    def insert_version(
        self,
        *,
        service_name: str,
        version: str,
        semver: Any,
        status: LifecycleStatus,
        git_sha: str | None,
        image_tag: str | None,
        api_version: str,
        min_compatible_version: str | None,
        checksum_sha256: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            key = f"{service_name}:{version}"

            if key in self._versions:
                raise ConflictError(f"version already exists: {version}")

            now = utc_now()

            record = {
                "version_id": str(uuid.uuid4()),
                "service_name": service_name,
                "version": version,
                "major": semver.major,
                "minor": semver.minor,
                "patch": semver.patch,
                "prerelease": semver.prerelease,
                "build_metadata": semver.build,
                "git_sha": git_sha,
                "image_tag": image_tag,
                "api_version": api_version,
                "min_compatible_version": min_compatible_version,
                "status": status.value,
                "checksum_sha256": checksum_sha256,
                "metadata": metadata,
                "created_at": now,
                "released_at": None,
                "deprecated_at": None,
                "retired_at": None,
                "updated_at": now,
            }

            self._versions[key] = record
            self._dependencies[record["version_id"]] = []

            return record

    def get_version(self, service_name: str, version: str) -> dict[str, Any] | None:
        with self._lock:
            return self._versions.get(f"{service_name}:{version}")

    def list_versions(self, service_name: str) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(
                [
                    version
                    for version in self._versions.values()
                    if version["service_name"] == service_name
                ],
                key=lambda version: version["created_at"],
            )

    def get_dependencies(self, version_id: str) -> list[dict[str, str]]:
        with self._lock:
            return list(self._dependencies.get(version_id, []))

    def set_dependencies(
        self,
        version_id: str,
        dependencies: list[dict[str, str]],
    ) -> None:
        with self._lock:
            self._dependencies[version_id] = list(dependencies)

    def update_version_release(
        self,
        service_name: str,
        version: str,
        *,
        git_sha: str,
        image_tag: str,
        checksum_sha256: str,
    ) -> dict[str, Any]:
        with self._lock:
            key = f"{service_name}:{version}"
            record = self._versions.get(key)

            if record is None:
                raise NotFoundError(f"version not found: {version}")

            now = utc_now()

            updated = dict(record)
            updated["status"] = LifecycleStatus.RELEASED.value
            updated["git_sha"] = git_sha
            updated["image_tag"] = image_tag
            updated["checksum_sha256"] = checksum_sha256
            updated["released_at"] = now
            updated["updated_at"] = now

            self._versions[key] = updated

            return updated

    def update_version_status(
        self,
        service_name: str,
        version: str,
        status: LifecycleStatus,
    ) -> dict[str, Any]:
        with self._lock:
            key = f"{service_name}:{version}"
            record = self._versions.get(key)

            if record is None:
                raise NotFoundError(f"version not found: {version}")

            now = utc_now()

            updated = dict(record)
            updated["status"] = status.value
            updated["updated_at"] = now

            if status == LifecycleStatus.DEPRECATED:
                updated["deprecated_at"] = now

            if status == LifecycleStatus.RETIRED:
                updated["retired_at"] = now

            self._versions[key] = updated

            return updated

    def insert_event(
        self,
        *,
        version_id: str,
        event_type: str,
        actor: str,
        reason: str,
        details: dict[str, Any],
    ) -> None:
        with self._lock:
            self._events.append(
                {
                    "event_id": str(uuid.uuid4()),
                    "version_id": version_id,
                    "event_type": event_type,
                    "actor": actor,
                    "reason": reason,
                    "details": details,
                    "occurred_at": utc_now(),
                }
            )

    def get_released_versions(self, service_name: str) -> list[str]:
        with self._lock:
            versions = [
                version
                for version in self._versions.values()
                if version["service_name"] == service_name
                and version["status"] == LifecycleStatus.RELEASED.value
            ]

            versions.sort(
                key=lambda version: (
                    version["major"],
                    version["minor"],
                    version["patch"],
                ),
                reverse=True,
            )

            return [version["version"] for version in versions]


class PostgresRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def upsert_service(
        self,
        service_name: str,
        plane: str,
        description: str,
    ) -> dict[str, Any]:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO service_versioning.services (
                    service_name,
                    plane,
                    description
                )
                VALUES (%s, %s, %s)
                ON CONFLICT (service_name) DO UPDATE SET
                    plane = EXCLUDED.plane,
                    description = EXCLUDED.description,
                    updated_at = now()
                RETURNING
                    service_name,
                    plane,
                    description,
                    created_at,
                    updated_at
                """,
                (service_name, plane, description),
            ).fetchone()

        return {
            "service_name": row[0],
            "plane": row[1],
            "description": row[2],
            "created_at": row[3],
            "updated_at": row[4],
        }

    def get_service(self, service_name: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    service_name,
                    plane,
                    description,
                    created_at,
                    updated_at
                FROM service_versioning.services
                WHERE service_name = %s
                """,
                (service_name,),
            ).fetchone()

        if row is None:
            return None

        return {
            "service_name": row[0],
            "plane": row[1],
            "description": row[2],
            "created_at": row[3],
            "updated_at": row[4],
        }

    def list_services(self) -> list[dict[str, Any]]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    service_name,
                    plane,
                    description,
                    created_at,
                    updated_at
                FROM service_versioning.services
                ORDER BY service_name
                """
            ).fetchall()

        return [
            {
                "service_name": row[0],
                "plane": row[1],
                "description": row[2],
                "created_at": row[3],
                "updated_at": row[4],
            }
            for row in rows
        ]

    def insert_version(
        self,
        *,
        service_name: str,
        version: str,
        semver: Any,
        status: LifecycleStatus,
        git_sha: str | None,
        image_tag: str | None,
        api_version: str,
        min_compatible_version: str | None,
        checksum_sha256: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO service_versioning.service_versions (
                    service_name,
                    version,
                    major,
                    minor,
                    patch,
                    prerelease,
                    build_metadata,
                    git_sha,
                    image_tag,
                    api_version,
                    min_compatible_version,
                    status,
                    checksum_sha256,
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
                    %s::service_versioning.service_version_status,
                    %s,
                    %s
                )
                RETURNING
                    version_id,
                    service_name,
                    version,
                    status::text,
                    git_sha,
                    image_tag,
                    api_version,
                    min_compatible_version,
                    checksum_sha256,
                    metadata,
                    created_at,
                    released_at,
                    deprecated_at,
                    retired_at,
                    updated_at
                """,
                (
                    service_name,
                    version,
                    semver.major,
                    semver.minor,
                    semver.patch,
                    semver.prerelease,
                    semver.build,
                    git_sha,
                    image_tag,
                    api_version,
                    min_compatible_version,
                    status.value,
                    checksum_sha256,
                    Json(metadata),
                ),
            ).fetchone()

        return {
            "version_id": str(row[0]),
            "service_name": row[1],
            "version": row[2],
            "status": row[3],
            "git_sha": row[4],
            "image_tag": row[5],
            "api_version": row[6],
            "min_compatible_version": row[7],
            "checksum_sha256": row[8],
            "metadata": row[9],
            "created_at": row[10],
            "released_at": row[11],
            "deprecated_at": row[12],
            "retired_at": row[13],
            "updated_at": row[14],
        }

    def get_version(self, service_name: str, version: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    version_id,
                    service_name,
                    version,
                    status::text,
                    git_sha,
                    image_tag,
                    api_version,
                    min_compatible_version,
                    checksum_sha256,
                    metadata,
                    created_at,
                    released_at,
                    deprecated_at,
                    retired_at,
                    updated_at
                FROM service_versioning.service_versions
                WHERE service_name = %s
                  AND version = %s
                """,
                (service_name, version),
            ).fetchone()

        if row is None:
            return None

        return {
            "version_id": str(row[0]),
            "service_name": row[1],
            "version": row[2],
            "status": row[3],
            "git_sha": row[4],
            "image_tag": row[5],
            "api_version": row[6],
            "min_compatible_version": row[7],
            "checksum_sha256": row[8],
            "metadata": row[9],
            "created_at": row[10],
            "released_at": row[11],
            "deprecated_at": row[12],
            "retired_at": row[13],
            "updated_at": row[14],
        }

    def list_versions(self, service_name: str) -> list[dict[str, Any]]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    version_id,
                    service_name,
                    version,
                    status::text,
                    git_sha,
                    image_tag,
                    api_version,
                    min_compatible_version,
                    checksum_sha256,
                    metadata,
                    created_at,
                    released_at,
                    deprecated_at,
                    retired_at,
                    updated_at
                FROM service_versioning.service_versions
                WHERE service_name = %s
                ORDER BY created_at
                """,
                (service_name,),
            ).fetchall()

        return [
            {
                "version_id": str(row[0]),
                "service_name": row[1],
                "version": row[2],
                "status": row[3],
                "git_sha": row[4],
                "image_tag": row[5],
                "api_version": row[6],
                "min_compatible_version": row[7],
                "checksum_sha256": row[8],
                "metadata": row[9],
                "created_at": row[10],
                "released_at": row[11],
                "deprecated_at": row[12],
                "retired_at": row[13],
                "updated_at": row[14],
            }
            for row in rows
        ]

    def get_dependencies(self, version_id: str) -> list[dict[str, str]]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    depends_on_service_name,
                    min_version
                FROM service_versioning.service_version_dependencies
                WHERE version_id = %s
                ORDER BY depends_on_service_name
                """,
                (version_id,),
            ).fetchall()

        return [
            {
                "service_name": row[0],
                "min_version": row[1],
            }
            for row in rows
        ]

    def set_dependencies(
        self,
        version_id: str,
        dependencies: list[dict[str, str]],
    ) -> None:
        with self._pool.connection() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    DELETE FROM service_versioning.service_version_dependencies
                    WHERE version_id = %s
                    """,
                    (version_id,),
                )

                for dependency in dependencies:
                    conn.execute(
                        """
                        INSERT INTO service_versioning.service_version_dependencies (
                            version_id,
                            depends_on_service_name,
                            min_version
                        )
                        VALUES (%s, %s, %s)
                        """,
                        (
                            version_id,
                            dependency["service_name"],
                            dependency["min_version"],
                        ),
                    )

    def update_version_release(
        self,
        service_name: str,
        version: str,
        *,
        git_sha: str,
        image_tag: str,
        checksum_sha256: str,
    ) -> dict[str, Any]:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE service_versioning.service_versions
                SET
                    status = 'RELEASED'::service_versioning.service_version_status,
                    git_sha = %s,
                    image_tag = %s,
                    checksum_sha256 = %s,
                    released_at = now(),
                    updated_at = now()
                WHERE service_name = %s
                  AND version = %s
                RETURNING
                    version_id,
                    service_name,
                    version,
                    status::text,
                    git_sha,
                    image_tag,
                    api_version,
                    min_compatible_version,
                    checksum_sha256,
                    metadata,
                    created_at,
                    released_at,
                    deprecated_at,
                    retired_at,
                    updated_at
                """,
                (
                    git_sha,
                    image_tag,
                    checksum_sha256,
                    service_name,
                    version,
                ),
            ).fetchone()

        if row is None:
            raise NotFoundError(f"version not found: {version}")

        return {
            "version_id": str(row[0]),
            "service_name": row[1],
            "version": row[2],
            "status": row[3],
            "git_sha": row[4],
            "image_tag": row[5],
            "api_version": row[6],
            "min_compatible_version": row[7],
            "checksum_sha256": row[8],
            "metadata": row[9],
            "created_at": row[10],
            "released_at": row[11],
            "deprecated_at": row[12],
            "retired_at": row[13],
            "updated_at": row[14],
        }

    def update_version_status(
        self,
        service_name: str,
        version: str,
        status: LifecycleStatus,
    ) -> dict[str, Any]:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE service_versioning.service_versions
                SET
                    status = %s::service_versioning.service_version_status,
                    deprecated_at = CASE
                        WHEN %s = 'DEPRECATED' THEN now()
                        ELSE deprecated_at
                    END,
                    retired_at = CASE
                        WHEN %s = 'RETIRED' THEN now()
                        ELSE retired_at
                    END,
                    updated_at = now()
                WHERE service_name = %s
                  AND version = %s
                RETURNING
                    version_id,
                    service_name,
                    version,
                    status::text,
                    git_sha,
                    image_tag,
                    api_version,
                    min_compatible_version,
                    checksum_sha256,
                    metadata,
                    created_at,
                    released_at,
                    deprecated_at,
                    retired_at,
                    updated_at
                """,
                (
                    status.value,
                    status.value,
                    status.value,
                    service_name,
                    version,
                ),
            ).fetchone()

        if row is None:
            raise NotFoundError(f"version not found: {version}")

        return {
            "version_id": str(row[0]),
            "service_name": row[1],
            "version": row[2],
            "status": row[3],
            "git_sha": row[4],
            "image_tag": row[5],
            "api_version": row[6],
            "min_compatible_version": row[7],
            "checksum_sha256": row[8],
            "metadata": row[9],
            "created_at": row[10],
            "released_at": row[11],
            "deprecated_at": row[12],
            "retired_at": row[13],
            "updated_at": row[14],
        }

    def insert_event(
        self,
        *,
        version_id: str,
        event_type: str,
        actor: str,
        reason: str,
        details: dict[str, Any],
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO service_versioning.service_version_events (
                    version_id,
                    event_type,
                    actor,
                    reason,
                    details
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    version_id,
                    event_type,
                    actor,
                    reason,
                    Json(details),
                ),
            )

    def get_released_versions(self, service_name: str) -> list[str]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT version
                FROM service_versioning.service_versions
                WHERE service_name = %s
                  AND status = 'RELEASED'
                ORDER BY
                    major DESC,
                    minor DESC,
                    patch DESC
                """,
                (service_name,),
            ).fetchall()

        return [row[0] for row in rows]


def apply_migrations(database_url: str, migrations_dir: str) -> None:
    path = Path(migrations_dir)

    if not path.exists():
        raise FileNotFoundError(f"migrations directory does not exist: {path}")

    migrations = sorted(path.glob("*.sql"))

    if not migrations:
        raise FileNotFoundError(f"no SQL migrations found in {path}")

    with psycopg.connect(database_url, autocommit=True) as conn:
        for migration in migrations:
            conn.execute(migration.read_text(encoding="utf-8"))