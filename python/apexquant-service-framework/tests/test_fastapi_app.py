from fastapi.testclient import TestClient

from apexquant_service_framework.fastapi_app import create_service_app
from apexquant_service_framework.service_contract import (
    FailClosedPolicy,
    ServiceDescriptor,
    ServicePlane,
)
from apexquant_service_framework.settings import ServiceFrameworkSettings


def test_service_framework_endpoints() -> None:
    settings = ServiceFrameworkSettings(
        service_name="test-service",
        service_version="0.1.0",
        environment="sandbox",
        plane=ServicePlane.AI,
        fail_closed_policy=FailClosedPolicy.READ_ONLY,
        registration_required=False,
    )

    descriptor = ServiceDescriptor(
        service_name="test-service",
        version="0.1.0",
        environment="sandbox",
        plane=ServicePlane.AI,
        fail_closed_policy=FailClosedPolicy.READ_ONLY,
    )

    app = create_service_app(settings, descriptor)

    with TestClient(app) as client:
        health = client.get("/healthz")
        ready = client.get("/readyz")
        metrics = client.get("/metrics")

        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        assert ready.status_code == 200
        assert ready.json()["ready"] is True

        assert metrics.status_code == 200
        assert b"apex_service_requests_total" in metrics.content