from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, Sequence
from uuid import UUID

from apexquant_event_bus.models import (
    EventEnvelope,
    EventBusVerificationReport,
    TopicSpec,
)


class DatabaseConnection(Protocol):
    def execute(
        self,
        query: str,
        parameters: Sequence[Any] | None = None,
        /,
    ) -> Any:
        raise NotImplementedError

    def commit(self) -> None:
        raise NotImplementedError


def persist_topics(connection: DatabaseConnection, topics: list[TopicSpec]) -> None:
    for topic in topics:
        connection.execute(
            """
            INSERT INTO event_bus.topics (
                topic_name,
                domain,
                description,
                partitions,
                replication_factor,
                retention_ms,
                cleanup_policy
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            ON CONFLICT (topic_name) DO UPDATE SET
                domain = EXCLUDED.domain,
                description = EXCLUDED.description,
                partitions = EXCLUDED.partitions,
                replication_factor = EXCLUDED.replication_factor,
                retention_ms = EXCLUDED.retention_ms,
                cleanup_policy = EXCLUDED.cleanup_policy,
                updated_at = now()
            """,
            (
                topic.name,
                topic.domain,
                topic.description,
                topic.partitions,
                topic.replication_factor,
                topic.retention_ms,
                topic.cleanup_policy,
            ),
        )

    connection.commit()


def persist_verification_report(
    connection: DatabaseConnection,
    report: EventBusVerificationReport,
) -> None:
    import json

    connection.execute(
        """
        INSERT INTO event_bus.verification_runs (
            environment,
            bootstrap_servers,
            generated_at,
            ok,
            missing_topics,
            observed_topics
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
        """,
        (
            report.environment,
            report.bootstrap_servers,
            report.generated_at,
            report.ok,
            json.dumps(report.missing_topics),
            json.dumps(report.observed_topics),
        ),
    )

    connection.commit()


def enqueue_outbox_event(
    connection: DatabaseConnection,
    envelope: EventEnvelope,
    aggregate_id: str | None = None,
) -> None:
    import json

    connection.execute(
        """
        INSERT INTO event_bus.event_outbox (
            event_id,
            topic,
            event_type,
            event_version,
            aggregate_id,
            idempotency_key,
            payload,
            headers,
            status
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            'PENDING'
        )
        ON CONFLICT (event_id) DO NOTHING
        """,
        (
            envelope.event_id,
            envelope.topic,
            envelope.event_type,
            envelope.event_version,
            aggregate_id,
            envelope.idempotency_key,
            envelope.payload,
            json.dumps(
                {
                    "event_id": str(envelope.event_id),
                    "producer_service": envelope.producer_service,
                    "producer_plane": envelope.producer_plane,
                }
            ),
        ),
    )

    connection.commit()


def mark_outbox_event_published(
    connection: DatabaseConnection,
    event_id: UUID,
) -> None:
    connection.execute(
        """
        UPDATE event_bus.event_outbox
        SET
            status = 'PUBLISHED',
            published_at = now()
        WHERE event_id = %s
        """,
        (event_id,),
    )

    connection.commit()


def mark_outbox_event_failed(
    connection: DatabaseConnection,
    event_id: UUID,
) -> None:
    connection.execute(
        """
        UPDATE event_bus.event_outbox
        SET
            status = 'FAILED',
            attempts = attempts + 1
        WHERE event_id = %s
        """,
        (event_id,),
    )

    connection.commit()