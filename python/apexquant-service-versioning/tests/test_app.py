from fastapi.testclient import TestClient

from apexquant_service_versioning.app import create_service_versioning_app
from apexquant_service_versioning.settings import ServiceVersioningSettings


def build_client() -> TestClient:
    settings = ServiceVersioningSettings(database_url=None)
    app = create_service_versioning_app(settings)

    return TestClient(app)


def test_health_endpoint() -> None:
    with build_client() as client:
        response = client.get("/healthz")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_service_and_version_api_flow() -> None:
    with build_client() as client:
        register_response = client.post(
            "/v1/services",
            json={
                "service_name": "api-gateway",
                "plane": "CONTROL",
                "description": "API gateway",
            },
        )

        assert register_response.status_code == 201

        create_response = client.post(
            "/v1/services/api-gateway/versions",
            json={
                "version": "1.0.0",
                "api_version": "v1",
                "metadata": {"team": "platform"},
            },
        )

        assert create_response.status_code == 201

        release_response = client.post(
            "/v1/services/api-gateway/versions/1.0.0/release",
            json={
                "git_sha": "a" * 40,
                "image_tag": "apexquant/api-gateway:1.0.0",
                "checksum_sha256": "f" * 64,
                "actor": "release-manager",
                "reason": "initial release",
            },
        )

        assert release_response.status_code == 200
        assert release_response.json()["status"] == "RELEASED"

        compatibility_response = client.get(
            "/v1/services/api-gateway/versions/1.0.0/compatibility"
        )

        assert compatibility_response.status_code == 200
        assert compatibility_response.json()["ok"] is True