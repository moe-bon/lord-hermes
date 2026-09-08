from __future__ import annotations

from pathlib import Path

import yaml

from apexquant_env_config.validator import validate_environment


def write_local_manifest(tmp_path: Path) -> Path:
    environment_dir = tmp_path / "local"
    environment_dir.mkdir(parents=True)

    manifest = {
        "environment": "local",
        "display_name": "Local Development",
        "trading_mode": "DEVELOPMENT",
        "live_capital_allowed": False,
        "fail_closed_default": True,
        "risk_enforcement_required": True,
        "ai_direct_execution_allowed": False,
        "observability_required": True,
        "networks": {
            "platform": "apexquant-platform",
            "data": "apexquant-data",
            "observability": "apexquant-observability",
        },
        "services": {
            "service_framework": {
                "enabled": True,
                "log_level": "INFO",
                "metrics_enabled": True,
            }
        },
        "infrastructure": {
            "postgres": {
                "host": "postgres",
                "port": 5432,
                "database": "apexquant",
                "user": "${POSTGRES_USER}",
                "password": "${POSTGRES_PASSWORD}",
                "ssl_mode": "disable",
            },
            "redis": {
                "host": "redis",
                "port": 6379,
                "database_index": 0,
            },
            "kafka": {
                "bootstrap_servers": "redpanda:9092",
                "security_protocol": "PLAINTEXT",
            },
            "object_storage": {
                "endpoint": "http://minio:9000",
                "access_key": "${MINIO_ROOT_USER}",
                "secret_key": "${MINIO_ROOT_PASSWORD}",
                "secure": False,
            },
        },
    }

    manifest_path = environment_dir / "environment.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")

    return manifest_path


def test_validate_local_manifest_success(tmp_path: Path) -> None:
    write_local_manifest(tmp_path)

    report = validate_environment(tmp_path, "local")

    assert report.ok
    assert report.errors_count == 0
    assert "POSTGRES_USER" in report.required_env_vars
    assert "POSTGRES_PASSWORD" in report.required_env_vars


def test_validate_missing_manifest_fails(tmp_path: Path) -> None:
    report = validate_environment(tmp_path, "local")

    assert not report.ok
    assert any(
        violation.code == "MANIFEST_MISSING" for violation in report.violations
    )


def test_validate_missing_process_env_vars(tmp_path: Path) -> None:
    write_local_manifest(tmp_path)

    report = validate_environment(
        tmp_path,
        "local",
        check_process_env=True,
        process_env={},
    )

    assert not report.ok
    assert any(
        violation.code == "REQUIRED_ENV_VAR_MISSING"
        for violation in report.violations
    )


def test_validate_process_env_vars_present(tmp_path: Path) -> None:
    write_local_manifest(tmp_path)

    report = validate_environment(
        tmp_path,
        "local",
        check_process_env=True,
        process_env={
            "POSTGRES_USER": "apex",
            "POSTGRES_PASSWORD": "apex",
            "MINIO_ROOT_USER": "apex",
            "MINIO_ROOT_PASSWORD": "apexquant-minio",
        },
    )

    assert report.ok