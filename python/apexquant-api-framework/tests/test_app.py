from fastapi.testclient import TestClient

from apexquant_api_framework import create_api_app


def build_client() -> TestClient:
    app = create_api_app(
        service_name="test-service",
        service_version="0.10.0",
        environment="local",
        plane="CONTROL",
        description="test api framework",
    )

    return TestClient(app)


def test_health_endpoint() -> None:
    client = build_client()

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_info_endpoint() -> None:
    client = build_client()

    response = client.get("/v1/api/info")

    assert response.status_code == 200

    payload = response.json()

    assert payload["service_name"] == "test-service"
    assert payload["environment"] == "local"
    assert payload["plane"] == "CONTROL"
    assert payload["api_version"] == "v1"


def test_unknown_route_returns_structured_error() -> None:
    client = build_client()

    response = client.get("/does-not-exist")

    assert response.status_code == 404

    payload = response.json()

    assert payload["error"]["code"] == "HTTP_ERROR"


def test_request_id_header_is_present() -> None:
    client = build_client()

    response = client.get("/healthz")

    assert "x-request-id" in response.headers
    assert response.headers["x-apex-service"] == "test-service"