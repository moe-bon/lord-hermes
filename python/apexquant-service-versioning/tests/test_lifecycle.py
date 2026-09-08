import pytest

from apexquant_service_versioning.errors import InvalidTransitionError, VersioningError
from apexquant_service_versioning.models import ServiceCreate, VersionCreate
from apexquant_service_versioning.repository import InMemoryRepository
from apexquant_service_versioning.service import VersioningService


def build_service() -> VersioningService:
    repository = InMemoryRepository()
    service = VersioningService(repository)

    service.register_service(
        ServiceCreate(
            service_name="auth-core",
            plane="CONTROL",
            description="Authentication service",
        )
    )

    return service


def test_version_lifecycle() -> None:
    service = build_service()

    created = service.create_version(
        "auth-core",
        VersionCreate(version="1.0.0"),
    )

    assert created.status.value == "DRAFT"

    released = service.release_version(
        service_name="auth-core",
        version="1.0.0",
        git_sha="a" * 40,
        image_tag="apexquant/auth-core:1.0.0",
        checksum_sha256="b" * 64,
        actor="release-manager",
        reason="initial release",
    )

    assert released.status.value == "RELEASED"

    deprecated = service.deprecate_version(
        service_name="auth-core",
        version="1.0.0",
        actor="release-manager",
        reason="superseded",
    )

    assert deprecated.status.value == "DEPRECATED"

    retired = service.retire_version(
        service_name="auth-core",
        version="1.0.0",
        actor="release-manager",
        reason="end of life",
    )

    assert retired.status.value == "RETIRED"


def test_prerelease_version_cannot_be_released() -> None:
    service = build_service()

    service.create_version(
        "auth-core",
        VersionCreate(version="1.0.0-rc.1"),
    )

    with pytest.raises(VersioningError):
        service.release_version(
            service_name="auth-core",
            version="1.0.0-rc.1",
            git_sha="a" * 40,
            image_tag="apexquant/auth-core:1.0.0-rc.1",
            checksum_sha256="b" * 64,
            actor="release-manager",
            reason="rc release",
        )


def test_invalid_transition_from_draft_to_deprecated() -> None:
    service = build_service()

    service.create_version(
        "auth-core",
        VersionCreate(version="1.1.0"),
    )

    with pytest.raises(InvalidTransitionError):
        service.deprecate_version(
            service_name="auth-core",
            version="1.1.0",
            actor="release-manager",
            reason="invalid",
        )