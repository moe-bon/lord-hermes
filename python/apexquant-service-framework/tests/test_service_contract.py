import pytest
from pydantic import ValidationError

from apexquant_service_framework.service_contract import (
    FailClosedPolicy,
    ServiceDescriptor,
    ServicePlane,
)


def test_valid_descriptor_generates_deterministic_service_id() -> None:
    descriptor = ServiceDescriptor(
        service_name="test-service",
        version="0.1.0",
        environment="sandbox",
        plane=ServicePlane.AI,
        fail_closed_policy=FailClosedPolicy.READ_ONLY,
    )

    assert descriptor.service_id == "sandbox:test-service:0.1.0"


def test_ai_plane_cannot_hold_broker_write() -> None:
    with pytest.raises(ValidationError):
        ServiceDescriptor(
            service_name="test-service",
            version="0.1.0",
            environment="sandbox",
            plane=ServicePlane.AI,
            fail_closed_policy=FailClosedPolicy.READ_ONLY,
            permissions=["BROKER_WRITE"],
        )


def test_trading_plane_cannot_submit_orders() -> None:
    with pytest.raises(ValidationError):
        ServiceDescriptor(
            service_name="test-service",
            version="0.1.0",
            environment="sandbox",
            plane=ServicePlane.TRADING,
            fail_closed_policy=FailClosedPolicy.HALT_TRADING,
            permissions=["ORDER_SUBMIT"],
        )


def test_risk_plane_can_submit_orders() -> None:
    descriptor = ServiceDescriptor(
        service_name="test-service",
        version="0.1.0",
        environment="sandbox",
        plane=ServicePlane.RISK,
        fail_closed_policy=FailClosedPolicy.HALT_TRADING,
        permissions=["ORDER_SUBMIT"],
    )

    assert "ORDER_SUBMIT" in descriptor.permissions