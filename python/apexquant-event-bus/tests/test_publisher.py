import pytest

from apexquant_event_bus.models import EventEnvelope
from apexquant_event_bus.publisher import EventPublisher, EventBusError
from apexquant_event_bus.topics import TopicRegistry


class FakeProducer:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_and_wait(
        self,
        topic: str,
        *,
        value: bytes,
        key: bytes | None = None,
        headers: list[tuple[str, bytes]] | None = None,
    ) -> None:
        self.sent.append(
            {
                "topic": topic,
                "value": value,
                "key": key,
                "headers": headers,
            }
        )


@pytest.mark.asyncio
async def test_publisher_sends_registered_topic() -> None:
    producer = FakeProducer()
    publisher = EventPublisher(
        producer,
        service_name="test-service",
        plane="CONTROL",
        registry=TopicRegistry.canonical(),
    )

    envelope = EventEnvelope.model_validate(
        {
            "event_id": "0d9f0f6e-5f7a-4d8a-8b1c-8c1f5f2f0a11",
            "event_type": "platform.event-bus.heartbeat",
            "event_version": 1,
            "occurred_at": "2026-01-01T00:00:00Z",
            "producer_service": "test-service",
            "producer_plane": "CONTROL",
            "idempotency_key": "heartbeat:test",
            "payload": {"status": "ok"},
        }
    )

    await publisher.publish(envelope)

    assert len(producer.sent) == 1
    assert producer.sent[0]["topic"] == "platform.event-bus.heartbeat.v1"


@pytest.mark.asyncio
async def test_publisher_rejects_unregistered_topic() -> None:
    producer = FakeProducer()
    publisher = EventPublisher(
        producer,
        service_name="test-service",
        plane="CONTROL",
        registry=TopicRegistry.canonical(),
    )

    envelope = EventEnvelope.model_validate(
        {
            "event_id": "0d9f0f6e-5f7a-4d8a-8b1c-8c1f5f2f0a12",
            "event_type": "custom.domain.event",
            "event_version": 1,
            "occurred_at": "2026-01-01T00:00:00Z",
            "producer_service": "test-service",
            "producer_plane": "CONTROL",
            "idempotency_key": "custom:test",
            "payload": {},
        }
    )

    with pytest.raises(EventBusError):
        await publisher.publish(envelope)