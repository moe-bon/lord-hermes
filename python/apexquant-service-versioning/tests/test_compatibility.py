from apexquant_service_versioning.models import (
    DependencySpec,
    ServiceCreate,
    VersionCreate,
)
from apexquant_service_versioning.repository import InMemoryRepository
from apexquant_service_versioning.service import VersioningService


def test_dependency_compatibility_resolution() -> None:
    repository = InMemoryRepository()
    service = VersioningService(repository)

    service.register_service(
        ServiceCreate(
            service_name="event-bus-core",
            plane="PLATFORM",
            description="Event bus service",
        )
    )

    service.register_service(
        ServiceCreate(
            service_name="audit-core",
            plane="OBSERVABILITY",
            description="Audit service",
        )
    )

    service.create_version(
        "event-bus-core",
        VersionCreate(version="1.2.0"),
    )

    service.release_version(
        service_name="event-bus-core",
        version="1.2.0",
        git_sha="a" * 40,
        image_tag="apexquant/event-bus-core:1.2.0",
        checksum_sha256="c" * 64,
        actor="release-manager",
        reason="release",
    )

    service.create_version(
        "event-bus-core",
        VersionCreate(version="1.3.0"),
    )

    service.release_version(
        service_name="event-bus-core",
        version="1.3.0",
        git_sha="b" * 40,
        image_tag="apexquant/event-bus-core:1.3.0",
        checksum_sha256="d" * 64,
        actor="release-manager",
        reason="release",
    )

    service.create_version(
        "audit-core",
        VersionCreate(
            version="1.0.0",
            dependencies=[
                DependencySpec(
                    service_name="event-bus-core",
                    min_version="1.2.0",
                )
            ],
        ),
    )

    service.release_version(
        service_name="audit-core",
        version="1.0.0",
        git_sha="c" * 40,
        image_tag="apexquant/audit-core:1.0.0",
        checksum_sha256="e" * 64,
        actor="release-manager",
        reason="release",
    )

    report = service.check_compatibility("audit-core", "1.0.0")

    assert report.ok is True
    assert report.dependencies[0].resolved_version == "1.3.0"