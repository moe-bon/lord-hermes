from __future__ import annotations

from pathlib import Path

import yaml

from apexquant_env_config.cli import main


def write_invalid_environment(tmp_path: Path) -> None:
    environment_dir = tmp_path / "local"
    environment_dir.mkdir(parents=True)

    manifest = {
        "environment": "local",
        "display_name": "Local Development",
        "trading_mode": "PRODUCTION",
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

    (environment_dir / "environment.yaml").write_text(
        yaml.safe_dump(manifest),
        encoding="utf-8",
    )


def test_cli_fails_for_invalid_environment(tmp_path: Path) -> None:
    write_invalid_environment(tmp_path)

    exit_code = main(
        [
            "--environments-root",
            str(tmp_path),
            "--environment",
            "local",
            "--json",
        ]
    )

    assert exit_code == 1


def test_cli_returns_two_for_missing_root(tmp_path: Path) -> None:
    exit_code = main(
        [
            "--environments-root",
            str(tmp_path / "does-not-exist"),
            "--environment",
            "local",
            "--json",
        ]
    )

    assert exit_code == 2