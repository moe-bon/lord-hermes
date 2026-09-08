from fastapi.testclient import TestClient

from apexquant_disaster_recovery.app import create_dr_app
from apexquant_disaster_recovery.backup_provider import InMemoryBackupStatusProvider
from apexquant_disaster_recovery.health import NullHealthChecker
from apexquant_disaster_recovery.repository import InMemoryDRRepository
from apexquant_disaster_recovery.service import DisasterRecoveryService


def build_client() -> TestClient:
    repository = InMemoryDRRepository()
    backup_provider = InMemoryBackupStatusProvider()
    health_checker = NullHealthChecker()

    service = DisasterRecoveryService(
        repository=repository,
        backup_provider=backup_provider,
        health_checker=health_checker,
        enable_health_checks=False,
    )

    app = create_dr_app(service)

    return TestClient(app)


def test_health_endpoint() -> None:
    client = build_client()

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_plan_component_and_drill_flow() -> None:
    client = build_client()

    plan_response = client.post(
        "/v1/dr/plans",
        json={
            "name": "platform-disaster-recovery-plan",
            "environment": "local",
            "rpo_seconds": 3600,
            "rto_seconds": 3600,
        },
    )

    assert plan_response.status_code == 201

    plan = plan_response.json()
    plan_id = plan["plan_id"]

    component_response = client.post(
        f"/v1/dr/plans/{plan_id}/components",
        json={
            "component_name": "postgresql-primary",
            "component_type": "DATABASE",
            "recovery_strategy": "MANUAL",
            "priority": 1,
        },
    )

    assert component_response.status_code == 201

    activate_response = client.post(
        f"/v1/dr/plans/{plan_id}/activate",
        json={"actor": "test"},
    )

    assert activate_response.status_code == 200

    drill_response = client.post(
        f"/v1/dr/plans/{plan_id}/drills",
        json={"actor": "test", "trigger": "unit-test"},
    )

    assert drill_response.status_code == 201

    drill = drill_response.json()

    assert drill["status"] == "SUCCEEDED"

    readiness_response = client.get(f"/v1/dr/plans/{plan_id}/readiness")

    assert readiness_response.status_code == 200

    readiness = readiness_response.json()

    assert readiness["state"] in {"READY", "DEGRADED"}