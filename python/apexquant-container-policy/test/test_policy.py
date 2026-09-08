from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from apexquant_container_policy.compose import load_compose
from apexquant_container_policy.policy import verify_document


def write_compose(tmp_path: Path, document: dict[str, Any]) -> Path:
    compose_path = tmp_path / "docker-compose.yaml"
    compose_path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return compose_path


def valid_compose_document() -> dict[str, Any]:
    return {
        "services": {
            "test-service": {
                "image": "apexquant/test-service:0.1.0",
                "user": "10001",
                "read_only": True,
                "security_opt": ["no-new-privileges:true"],
                "cap_drop": ["ALL"],
                "healthcheck": {
                    "test": ["CMD", "curl", "-sf", "http://127.0.0.1:8080/healthz"],
                    "interval": "5s",
                    "timeout": "3s",
                    "retries": 20,
                },
                "networks": {
                    "platform": None,
                },
                "labels": {
                    "apexquant.managed": "true",
                    "apexquant.service.name": "test-service",
                    "apexquant.service.plane": "CONTROL",
                    "apexquant.environment": "local",
                    "apexquant.feature": "0.3",
                    "apexquant.version": "0.1.0",
                    "apexquant.fail_closed_policy": "SHUTDOWN",
                },
                "deploy": {
                    "resources": {
                        "limits": {
                            "memory": "256M",
                            "cpus": "0.50",
                        }
                    }
                },
                "environment": {
                    "APEX_ENVIRONMENT": "local",
                },
            }
        },
        "networks": {
            "platform": None,
        },
    }


def test_valid_compose_passes(tmp_path: Path) -> None:
    compose_path = write_compose(tmp_path, valid_compose_document())
    document = load_compose(compose_path)

    report = verify_document(document)

    assert report.ok
    assert report.errors_count == 0
    assert report.warnings_count == 0
    assert report.services_checked == ["test-service"]


def test_latest_image_tag_is_rejected(tmp_path: Path) -> None:
    raw = valid_compose_document()
    raw["services"]["test-service"]["image"] = "apexquant/test-service:latest"

    compose_path = write_compose(tmp_path, raw)
    document = load_compose(compose_path)

    report = verify_document(document)

    assert not report.ok
    assert any(
        violation.code == "LATEST_IMAGE_TAG_FORBIDDEN"
        for violation in report.violations
    )


def test_missing_healthcheck_is_rejected(tmp_path: Path) -> None:
    raw = valid_compose_document()
    del raw["services"]["test-service"]["healthcheck"]

    compose_path = write_compose(tmp_path, raw)
    document = load_compose(compose_path)

    report = verify_document(document)

    assert not report.ok
    assert any(
        violation.code == "HEALTHCHECK_MISSING"
        for violation in report.violations
    )


def test_privileged_container_is_rejected(tmp_path: Path) -> None:
    raw = valid_compose_document()
    raw["services"]["test-service"]["privileged"] = True

    compose_path = write_compose(tmp_path, raw)
    document = load_compose(compose_path)

    report = verify_document(document)

    assert not report.ok
    assert any(
        violation.code == "PRIVILEGED_FORBIDDEN"
        for violation in report.violations
    )


def test_root_user_is_rejected(tmp_path: Path) -> None:
    raw = valid_compose_document()
    raw["services"]["test-service"]["user"] = "root"

    compose_path = write_compose(tmp_path, raw)
    document = load_compose(compose_path)

    report = verify_document(document)

    assert not report.ok
    assert any(
        violation.code == "ROOT_USER_FORBIDDEN"
        for violation in report.violations
    )


def test_missing_resource_limits_are_rejected(tmp_path: Path) -> None:
    raw = valid_compose_document()
    del raw["services"]["test-service"]["deploy"]

    compose_path = write_compose(tmp_path, raw)
    document = load_compose(compose_path)

    report = verify_document(document)

    assert not report.ok
    assert any(
        violation.code == "RESOURCE_LIMITS_MISSING"
        for violation in report.violations
    )


def test_literal_secret_environment_is_rejected(tmp_path: Path) -> None:
    raw = valid_compose_document()
    raw["services"]["test-service"]["environment"]["BROKER_API_SECRET"] = "hunter2"

    compose_path = write_compose(tmp_path, raw)
    document = load_compose(compose_path)

    report = verify_document(document)

    assert not report.ok
    assert any(
        violation.code == "LITERAL_SECRET_IN_ENVIRONMENT"
        for violation in report.violations
    )


def test_unmanaged_services_are_ignored(tmp_path: Path) -> None:
    raw = valid_compose_document()
    raw["services"]["postgres"] = {
        "image": "postgres:16-alpine",
        "environment": {
            "POSTGRES_PASSWORD": "apex",
        },
    }

    compose_path = write_compose(tmp_path, raw)
    document = load_compose(compose_path)

    report = verify_document(document)

    assert report.ok
    assert report.services_checked == ["test-service"]