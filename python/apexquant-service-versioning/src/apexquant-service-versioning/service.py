from __future__ import annotations

from typing import Any

from apexquant_service_versioning.errors import (
    ConflictError,
    InvalidTransitionError,
    NotFoundError,
    VersioningError,
)
from apexquant_service_versioning.models import (
    CompatibilityDependencyReport,
    CompatibilityReport,
    LifecycleStatus,
    ServiceCreate,
    ServiceVersion,
    VersionCreate,
)
from apexquant_service_versioning.semver import (
    SemVer,
    SemVerError,
    highest_compatible,
    parse_version,
)


class VersioningService:
    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def register_service(self, payload: ServiceCreate) -> dict[str, Any]:
        return self._repository.upsert_service(
            service_name=payload.service_name,
            plane=payload.plane.upper(),
            description=payload.description,
        )

    def list_services(self) -> list[dict[str, Any]]:
        return self._repository.list_services()

    def create_version(
        self,
        service_name: str,
        payload: VersionCreate,
    ) -> ServiceVersion:
        service = self._repository.get_service(service_name)

        if service is None:
            raise NotFoundError(f"service not found: {service_name}")

        try:
            semver = parse_version(payload.version)
        except SemVerError as exc:
            raise VersioningError(str(exc)) from exc

        if payload.min_compatible_version is not None:
            try:
                parse_version(payload.min_compatible_version)
            except SemVerError as exc:
                raise VersioningError(
                    f"invalid min_compatible_version: {exc}"
                ) from exc

        existing = self._repository.get_version(service_name, payload.version)

        if existing is not None:
            raise ConflictError(f"version already exists: {payload.version}")

        dependency_records: list[dict[str, str]] = []
        seen_dependencies: set[str] = set()

        for dependency in payload.dependencies:
            if dependency.service_name == service_name:
                raise VersioningError("a service cannot depend on itself")

            if dependency.service_name in seen_dependencies:
                raise VersioningError(
                    f"duplicate dependency: {dependency.service_name}"
                )

            dependency_service = self._repository.get_service(dependency.service_name)

            if dependency_service is None:
                raise NotFoundError(
                    f"dependency service not found: {dependency.service_name}"
                )

            try:
                parse_version(dependency.min_version)
            except SemVerError as exc:
                raise VersioningError(
                    f"invalid dependency min_version for {dependency.service_name}: {exc}"
                ) from exc

            seen_dependencies.add(dependency.service_name)

            dependency_records.append(
                {
                    "service_name": dependency.service_name,
                    "min_version": dependency.min_version,
                }
            )

        record = self._repository.insert_version(
            service_name=service_name,
            version=payload.version,
            semver=semver,
            status=LifecycleStatus.DRAFT,
            git_sha=payload.git_sha,
            image_tag=payload.image_tag,
            api_version=payload.api_version,
            min_compatible_version=payload.min_compatible_version,
            checksum_sha256=None,
            metadata=payload.metadata,
        )

        self._repository.set_dependencies(record["version_id"], dependency_records)

        self._repository.insert_event(
            version_id=record["version_id"],
            event_type="VERSION_CREATED",
            actor="system",
            reason="version draft created",
            details={"version": payload.version},
        )

        return self.get_version(service_name, payload.version)

    def get_version(self, service_name: str, version: str) -> ServiceVersion:
        record = self._repository.get_version(service_name, version)

        if record is None:
            raise NotFoundError(f"version not found: {version}")

        dependencies = self._repository.get_dependencies(record["version_id"])

        return ServiceVersion(
            version_id=record["version_id"],
            service_name=record["service_name"],
            version=record["version"],
            status=LifecycleStatus(record["status"]),
            git_sha=record["git_sha"],
            image_tag=record["image_tag"],
            api_version=record["api_version"],
            min_compatible_version=record["min_compatible_version"],
            checksum_sha256=record["checksum_sha256"],
            metadata=record["metadata"],
            created_at=record["created_at"],
            released_at=record["released_at"],
            deprecated_at=record["deprecated_at"],
            retired_at=record["retired_at"],
            dependencies=dependencies,
        )

    def list_versions(self, service_name: str) -> list[ServiceVersion]:
        service = self._repository.get_service(service_name)

        if service is None:
            raise NotFoundError(f"service not found: {service_name}")

        return [
            self.get_version(service_name, record["version"])
            for record in self._repository.list_versions(service_name)
        ]

    def release_version(
        self,
        service_name: str,
        version: str,
        git_sha: str,
        image_tag: str,
        checksum_sha256: str,
        actor: str,
        reason: str,
    ) -> ServiceVersion:
        current = self.get_version(service_name, version)

        if current.status != LifecycleStatus.DRAFT:
            raise InvalidTransitionError(
                f"cannot release version in status {current.status.value}"
            )

        semver = parse_version(version)

        if not semver.is_stable:
            raise VersioningError("only stable versions may be released")

        record = self._repository.update_version_release(
            service_name,
            version,
            git_sha=git_sha,
            image_tag=image_tag,
            checksum_sha256=checksum_sha256,
        )

        self._repository.insert_event(
            version_id=record["version_id"],
            event_type="VERSION_RELEASED",
            actor=actor,
            reason=reason,
            details={
                "git_sha": git_sha,
                "image_tag": image_tag,
                "checksum_sha256": checksum_sha256,
            },
        )

        return self.get_version(service_name, version)

    def deprecate_version(
        self,
        service_name: str,
        version: str,
        actor: str,
        reason: str,
    ) -> ServiceVersion:
        current = self.get_version(service_name, version)

        if current.status != LifecycleStatus.RELEASED:
            raise InvalidTransitionError(
                f"cannot deprecate version in status {current.status.value}"
            )

        record = self._repository.update_version_status(
            service_name,
            version,
            LifecycleStatus.DEPRECATED,
        )

        self._repository.insert_event(
            version_id=record["version_id"],
            event_type="VERSION_DEPRECATED",
            actor=actor,
            reason=reason,
            details={},
        )

        return self.get_version(service_name, version)

    def retire_version(
        self,
        service_name: str,
        version: str,
        actor: str,
        reason: str,
    ) -> ServiceVersion:
        current = self.get_version(service_name, version)

        if current.status != LifecycleStatus.DEPRECATED:
            raise InvalidTransitionError(
                f"cannot retire version in status {current.status.value}"
            )

        record = self._repository.update_version_status(
            service_name,
            version,
            LifecycleStatus.RETIRED,
        )

        self._repository.insert_event(
            version_id=record["version_id"],
            event_type="VERSION_RETIRED",
            actor=actor,
            reason=reason,
            details={},
        )

        return self.get_version(service_name, version)

    def check_compatibility(
        self,
        service_name: str,
        version: str,
    ) -> CompatibilityReport:
        current = self.get_version(service_name, version)

        if current.status != LifecycleStatus.RELEASED:
            raise InvalidTransitionError(
                "compatibility can only be checked for released versions"
            )

        dependency_reports: list[CompatibilityDependencyReport] = []
        ok = True

        for dependency in current.dependencies:
            candidates = self._repository.get_released_versions(
                dependency.service_name
            )

            resolved = highest_compatible(candidates, dependency.min_version)

            if resolved is None:
                ok = False

                dependency_reports.append(
                    CompatibilityDependencyReport(
                        service_name=dependency.service_name,
                        min_version=dependency.min_version,
                        resolved_version=None,
                        compatible=False,
                        reason="no released compatible dependency version found",
                    )
                )
            else:
                dependency_reports.append(
                    CompatibilityDependencyReport(
                        service_name=dependency.service_name,
                        min_version=dependency.min_version,
                        resolved_version=resolved,
                        compatible=True,
                        reason="compatible released version found",
                    )
                )

        return CompatibilityReport(
            service_name=service_name,
            version=version,
            ok=ok,
            dependencies=dependency_reports,
        )