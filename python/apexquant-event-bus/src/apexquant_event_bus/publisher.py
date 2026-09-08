from __future__ import annotations

from typing import Protocol

from apexquant_event_bus.models import EventEnvelope
from apexquant_event_bus.topics import TopicRegistry


class EventBusError(Exception):
    pass


class ProducerProtocol(Protocol):
    async def send_and_wait(
        self,
        topic: str,
        *,
        value: bytes,
        key: bytes | None = None,
        headers: list[tuple[str, bytes]] | None = None,
    ) -> None:
        raise NotImplementedError


class EventPublisher:
    def __init__(
        self,
        producer: ProducerProtocol,
        service_name: str,
        plane: str,
        registry: TopicRegistry | None = None,
    ) -> None:
        if not service_name.strip():
            raise EventBusError("service_name must not be empty")

        if not plane.strip():
            raise EventBusError("plane must not be empty")

        self._producer = producer
        self._service_name = service_name.strip()
        self._plane = plane.strip()
        self._registry = registry

    @property
    def service_name(self) -> str:
        return self._service_name

    @property
    def plane(self) -> str:
        return self._plane

    async def publish(self, envelope: EventEnvelope) -> None:
        topic = envelope.topic

        if self._registry is not None and not self._registry.contains(topic):
            raise EventBusError(f"topic is not registered: {topic}")

        value = envelope.model_dump_json().encode("utf-8")

        headers: list[tuple[str, bytes]] = [
            ("event_id", str(envelope.event_id).encode("utf-8")),
            ("event_type", envelope.event_type.encode("utf-8")),
            ("event_version", str(envelope.event_version).encode("utf-8")),
            ("occurred_at", envelope.occurred_at.isoformat().encode("utf-8")),
            ("producer_service", envelope.producer_service.encode("utf-8")),
            ("producer_plane", envelope.producer_plane.encode("utf-8")),
            ("idempotency_key", envelope.idempotency_key.encode("utf-8")),
        ]

        if envelope.correlation_id is not None:
            headers.append(("correlation_id", str(envelope.correlation_id).encode("utf-8")))

        if envelope.causation_id is not None:
            headers.append(("causation_id", str(envelope.causation_id).encode("utf-8")))

        if envelope.trace_id is not None:
            headers.append(("trace_id", envelope.trace_id.encode("utf-8")))

        await self._producer.send_and_wait(
            topic,
            value=value,
            key=envelope.idempotency_key.encode("utf-8"),
            headers=headers,
        )