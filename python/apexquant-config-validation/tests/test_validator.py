import pytest

from apexquant_config_validation.validator import ConfigValidator


@pytest.fixture
def validator() -> ConfigValidator:
    return ConfigValidator()


def valid_service_manifest() -> dict:
    return {
        "schema_version": "service_manifest/v1",
        "service_name": "execution-core",
        "service_version": "0.1.0",
        "environment": "local",
        "plane": "TRADING",
        "fail_closed_policy": "SHUTDOWN",
        "live_trading_allowed": False,
        "dependencies": ["postgres"],
        "endpoints": {
            "http": "http://execution-core:8080",
        },
        "resources": {
            "cpus": "1.0",
            "memory": "512M",
        },
    }


def valid_environment_manifest() -> dict:
    return {
        "schema_version": "environment_manifest/v1",
        "environment": "local",
        "trading_mode": "DEVELOPMENT",
        "live_capital_allowed": False,
        "fail_closed_default": True,
        "observability_required": True,
        "infrastructure": {
            "postgres": {
                "host": "postgres",
                "port": 5432,
                "user": "env://POSTGRES_USER",
                "password": "env://POSTGRES_PASSWORD",
            }
        },
    }


def test_valid_service_manifest_passes(validator: ConfigValidator) -> None:
    report = validator.validate("service_manifest/v1", valid_service_manifest())

    assert report.ok
    assert report.config_hash is not None


def test_valid_environment_manifest_passes(validator: ConfigValidator) -> None:
    report = validator.validate("environment_manifest/v1", valid_environment_manifest())

    assert report.ok
    assert report.config_hash is not None


def test_invalid_plane_fails(validator: ConfigValidator) -> None:
    manifest = valid_service_manifest()
    manifest["plane"] = "INVALID_PLANE"

    report = validator.validate("service_manifest/v1", manifest)

    assert not report.ok


def test_live_trading_only_allowed_in_production(validator: ConfigValidator) -> None:
    manifest = valid_service_manifest()
    manifest["live_trading_allowed"] = True

    report = validator.validate("service_manifest/v1", manifest)

    assert not report.ok


def test_literal_secret_fails(validator: ConfigValidator) -> None:
    manifest = valid_environment_manifest()
    manifest["infrastructure"]["postgres"]["password"] = "hunter2"

    report = validator.validate("environment_manifest/v1", manifest)

    assert not report.ok


def test_environment_trading_mode_mismatch_fails(validator: ConfigValidator) -> None:
    manifest = valid_environment_manifest()
    manifest["trading_mode"] = "PRODUCTION"

    report = validator.validate("environment_manifest/v1", manifest)

    assert not report.ok


def test_paper_environment_requires_fail_closed(validator: ConfigValidator) -> None:
    manifest = valid_environment_manifest()
    manifest["environment"] = "paper"
    manifest["trading_mode"] = "PAPER"
    manifest["fail_closed_default"] = False

    report = validator.validate("environment_manifest/v1", manifest)

    assert not report.ok