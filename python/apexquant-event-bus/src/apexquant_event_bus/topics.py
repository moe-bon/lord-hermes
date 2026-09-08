from __future__ import annotations

from apexquant_event_bus.models import TopicSpec

HEARTBEAT_TOPIC = "platform.event-bus.heartbeat.v1"
DEAD_LETTER_TOPIC = "platform.event-bus.dead-letter.v1"
AUDIT_TOPIC = "platform.audit.event.v1"
DIAGNOSTIC_TOPIC = "platform.observability.diagnostic.v1"

CANONICAL_TOPICS: list[TopicSpec] = [
    TopicSpec(
        name=HEARTBEAT_TOPIC,
        domain="platform",
        description="Event bus heartbeat events for service and infrastructure health",
        partitions=3,
        replication_factor=1,
        retention_ms=7 * 24 * 60 * 60 * 1000,
        cleanup_policy="delete",
    ),
    TopicSpec(
        name=DEAD_LETTER_TOPIC,
        domain="platform",
        description="Dead-letter events for failed processing and poison-pill containment",
        partitions=3,
        replication_factor=1,
        retention_ms=14 * 24 * 60 * 60 * 1000,
        cleanup_policy="delete",
    ),
    TopicSpec(
        name=AUDIT_TOPIC,
        domain="platform",
        description="Audit events for governance, security, and operational reconstruction",
        partitions=6,
        replication_factor=1,
        retention_ms=90 * 24 * 60 * 60 * 1000,
        cleanup_policy="delete",
    ),
    TopicSpec(
        name=DIAGNOSTIC_TOPIC,
        domain="platform",
        description="Observability diagnostics and operational telemetry",
        partitions=3,
        replication_factor=1,
        retention_ms=7 * 24 * 60 * 60 * 1000,
        cleanup_policy="delete",
    ),
]


class TopicRegistry:
    def __init__(self, topics: list[TopicSpec]) -> None:
        self._topics = {topic.name: topic for topic in topics}

    @classmethod
    def canonical(cls) -> TopicRegistry:
        return cls(CANONICAL_TOPICS)

    def contains(self, topic: str) -> bool:
        return topic in self._topics

    def get(self, topic: str) -> TopicSpec | None:
        return self._topics.get(topic)

    def specs(self) -> list[TopicSpec]:
        return list(self._topics.values())