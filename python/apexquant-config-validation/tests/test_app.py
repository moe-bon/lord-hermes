from fastapi.testclient import TestClient

from apexquant_config_validation.app import (
    ConfigValidationSettings,
    create_config_validation_app,
)


def build_client() -> TestClient:
    settings = ConfigValidationSettings(database_url=None)
    app = create_config_validation_app(settings)

    return TestClient(app)


def test_health_endpoint() -> None:
    with build_client() as client:
        response = client.get("/healthz")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_list_schemas() -> None:
    with build_client() as client:
        response = client.get("/v1/config/schemas")

        assert response.status_code == 200

        body = response.json()

        assert "service_manifest/v1" in body["schemas"]
        assert "environment_manifest/v1" in body["schemas"]


def test_validate_valid_service_manifest() -> None:
    with build_client() as client:
        response = client.post(
            "/v1/config/validate",
            json={
                "schema_key": "service_manifest/v1",
                "document": {
                    "schema_version": "service_manifest/v1",
                    "service_name": "execution-core",
                    "service_version": "0.1.0",
                    "environment": "local",
                    "plane": "TRADING",
                    "fail_closed_policy": "SHUTDOWN",
                    "live_trading_allowed": False,
                },
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["ok"] is True
        assert body["config_hash"] is not None


def test_validate_rejects_literal_secret() -> None:
    with build_client() as client:
        response = client.post(
            "/v1/config/validate",
            json={
                "schema_key": "environment_manifest/v1",
                "document": {
                    "schema_version": "environment_manifest/v1",
                    "environment": "local",
                    "trading_mode": "DEVELOPMENT",
                    "live_capital_allowed": False,
                    "fail_closed_default": True,
                    "observability_required": True,
                    "infrastructure": {
                        "postgres": {
                            "password": "hunter2",
                        }
                    },
                },
            },
        )

        assert response.status_code == 422

        body = response.json()

        assert body["ok"] is False