from __future__ import annotations

import pytest
from pydantic import ValidationError

from apexquant_env_config.models import (
    EnvironmentManifest,
    EnvironmentName,
    TradingMode,
)


def valid_manifest_payload() -> dict:
    return {
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


def test_valid_local_manifest_passes() -> None:
    manifest = EnvironmentManifest.model_validate(valid_manifest_payload())

    assert manifest.environment == EnvironmentName.LOCAL
    assert manifest.trading_mode == TradingMode.DEVELOPMENT
    assert manifest.fail_closed_default is True


def test_environment_and_trading_mode_must_match() -> None:
    payload = valid_manifest_payload()
    payload["trading_mode"] = "PRODUCTION"

    with pytest.raises(ValidationError):
        EnvironmentManifest.model_validate(payload)


def test_ai_direct_execution_is_forbidden() -> None:
    payload = valid_manifest_payload()
    payload["ai_direct_execution_allowed"] = True

    with pytest.raises(ValidationError):
        EnvironmentManifest.model_validate(payload)


def test_live_capital_only_allowed_in_production() -> None:
    payload = valid_manifest_payload()
    payload["live_capital_allowed"] = True

    with pytest.raises(ValidationError):
        EnvironmentManifest.model_validate(payload)


def test_paper_environment_requires_tls() -> None:
    payload = valid_manifest_payload()
    payload["environment"] = "paper"
    payload["trading_mode"] = "PAPER"
    payload["infrastructure"]["postgres"]["ssl_mode"] = "disable"

    with pytest.raises(ValidationError):
        EnvironmentManifest.model_validate(payload)