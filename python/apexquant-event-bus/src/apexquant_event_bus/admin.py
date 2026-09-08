from __future__ import annotations

from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import TopicAlreadyExistsError

from apexquant_event_bus.models import TopicSpec


async def ensure_topics(bootstrap_servers: str, topics: list[TopicSpec]) -> list[str]:
    admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap_servers)

    await admin.start()

    try:
        existing_topics = set(await admin.list_topics())

        to_create: list[NewTopic] = []

        for spec in topics:
            if spec.name in existing_topics:
                continue

            to_create.append(
                NewTopic(
                    name=spec.name,
                    num_partitions=spec.partitions,
                    replication_factor=spec.replication_factor,
                    topic_configs={
                        "retention.ms": str(spec.retention_ms),
                        "cleanup.policy": spec.cleanup_policy,
                    },
                )
            )

        created: list[str] = []

        if to_create:
            try:
                await admin.create_topics(to_create)
                created = [topic.name for topic in to_create]
            except TopicAlreadyExistsError:
                created = []

        return created
    finally:
        await admin.close()


async def list_broker_topics(bootstrap_servers: str) -> set[str]:
    admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap_servers)

    await admin.start()

    try:
        topics = await admin.list_topics()
        return set(topics)
    finally:
        await admin.close()