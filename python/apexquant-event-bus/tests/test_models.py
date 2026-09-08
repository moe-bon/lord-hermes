from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from apexquant_event_bus.models import EventEnvelope


def valid_envelope() -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        event_type="platform.event-bus.heartbeat",
        event_version=1,
        occurred_at=datetime.now(timezone.utc),
        producer_service="service-framework-core",
        producer_plane="CONTROL",
        idempotency_key="heartbeat:test",
        payload={"status": "ok"},
    )


def test_valid_envelope_passes() -> None:
    envelope = valid_envelope()

    assert envelope.topic == "platform.event-bus.heartbeat.v1"


def test_invalid_event_type_fails() -> None:
    with pytest.raises(ValidationError):
        EventEnvelope(
            event_id=uuid4(),
            event_type="Invalid.EventType",
            event_version=1,
            occurred_at=datetime.now(timezone.utc),
            producer_service="svc",
            producer_plane="CONTROL",
            idempotency_key="x",
        )


def test_empty_idempotency_key_fails() -> None:
    with pytest.raises(ValidationError):
        EventEnvelope(
            event_id=uuid4(),
            event_type="platform.event-bus.heartbeat",
            event_version=1,
            occurred_at=datetime.now(timezone.utc),
            producer_service="svc",
            producer_plane="CONTROL",
            idempotency_key="   ",
        )