import pytest

from apexquant_event_bus.consumer import process_message
from apexquant_event_bus.models import ConsumedMessage, EventEnvelope
from apexquant_event_bus.publisher import EventPublisher
from apexquant_event_bus.topics import TopicRegistry
from tests.test_publisher import FakeProducer


@pytest.mark.asyncio
async def test_process_message_success() -> None:
    envelope = EventEnvelope.model_validate(
        {
            "event_id": "0d9f0f6e-5f7a-4d8a-8b1c-8c1f5f2f0a13",
            "event_type": "platform.event-bus.heartbeat",
            "event_version": 1,
            "occurred_at": "2026-01-01T00:00:00Z",
            "producer_service": "test-service",
            "producer_plane": "CONTROL",
            "idempotency_key": "heartbeat:test",
            "payload": {"status": "ok"},
        }
    )

    message = ConsumedMessage(
        topic="platform.event-bus.heartbeat.v1",
        partition=0,
        offset=1,
        key="heartbeat:test",
        value=envelope.model_dump_json().encode("utf-8"),
    )

    called = False

    async def handler(event: EventEnvelope) -> None:
        nonlocal called
        called = True
        assert event.event_type == "platform.event-bus.heartbeat"

    result = await process_message(message, handler)

    assert result is True
    assert called is True


@pytest.mark.asyncio
async def test_process_message_failure_publishes_to_dlq() -> None:
    envelope = EventEnvelope.model_validate(
        {
            "event_id": "0d9f0f6e-5f7a-4d8a-8b1c-8c1f5f2f0a14",
            "event_type": "platform.event-bus.heartbeat",
            "event_version": 1,
            "occurred_at": "2026-01-01T00:00:00Z",
            "producer_service": "test-service",
            "producer_plane": "CONTROL",
            "idempotency_key": "heartbeat:test",
            "payload": {"status": "ok"},
        }
    )

    message = ConsumedMessage(
        topic="platform.event-bus.heartbeat.v1",
        partition=0,
        offset=2,
        key="heartbeat:test",
        value=envelope.model_dump_json().encode("utf-8"),
    )

    async def failing_handler(event: EventEnvelope) -> None:
        raise RuntimeError("processing failed")

    producer = FakeProducer()
    dlq_publisher = EventPublisher(
        producer,
        service_name="event-bus-verifier",
        plane="OBSERVABILITY",
        registry=TopicRegistry.canonical(),
    )

    result = await process_message(message, failing_handler, dlq_publisher)

    assert result is False
    assert len(producer.sent) == 1
    assert producer.sent[0]["topic"] == "platform.event-bus.dead-letter.v1"