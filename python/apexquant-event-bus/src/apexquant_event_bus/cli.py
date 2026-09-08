from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from apexquant_event_bus.admin import ensure_topics, list_broker_topics
from apexquant_event_bus.models import (
    ConsumedMessage,
    EventEnvelope,
    EventBusVerificationReport,
)
from apexquant_event_bus.publisher import EventPublisher
from apexquant_event_bus.topics import DEAD_LETTER_TOPIC, HEARTBEAT_TOPIC, TopicRegistry


def add_bootstrap_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--bootstrap-servers",
        default="localhost:9092",
    )
    parser.add_argument(
        "--environment",
        default="local",
    )
    parser.add_argument(
        "--database-url",
        default=None,
    )


def cmd_bootstrap(args: argparse.Namespace) -> int:
    registry = TopicRegistry.canonical()

    created_topics = asyncio.run(
        ensure_topics(args.bootstrap_servers, registry.specs())
    )

    if args.database_url:
        import psycopg
        from apexquant_event_bus.persistence import persist_topics

        with psycopg.connect(args.database_url) as connection:
            persist_topics(connection, registry.specs())

    print(
        json.dumps(
            {
                "bootstrap_servers": args.bootstrap_servers,
                "created_topics": created_topics,
                "registered_topics": [spec.name for spec in registry.specs()],
            },
            indent=2,
        )
    )

    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    observed_topics = asyncio.run(list_broker_topics(args.bootstrap_servers))
    registry = TopicRegistry.canonical()

    missing_topics = [
        spec.name for spec in registry.specs() if spec.name not in observed_topics
    ]

    report = EventBusVerificationReport(
        environment=args.environment,
        bootstrap_servers=args.bootstrap_servers,
        generated_at=datetime.now(timezone.utc),
        ok=not missing_topics,
        missing_topics=missing_topics,
        observed_topics=sorted(observed_topics),
    )

    if args.database_url:
        import psycopg
        from apexquant_event_bus.persistence import persist_verification_report

        with psycopg.connect(args.database_url) as connection:
            persist_verification_report(connection, report)

    print(report.model_dump_json(indent=2))

    return 0 if report.ok else 1


async def publish_heartbeat(args: argparse.Namespace) -> None:
    producer = AIOKafkaProducer(
        bootstrap_servers=args.bootstrap_servers,
        acks="all",
        enable_idempotence=True,
    )

    await producer.start()

    try:
        publisher = EventPublisher(
            producer,
            service_name=args.service_name,
            plane=args.plane,
            registry=TopicRegistry.canonical(),
        )

        envelope = EventEnvelope(
            event_id=uuid4(),
            event_type="platform.event-bus.heartbeat",
            event_version=1,
            occurred_at=datetime.now(timezone.utc),
            producer_service=args.service_name,
            producer_plane=args.plane,
            idempotency_key=f"heartbeat:{args.service_name}:{uuid4()}",
            payload={
                "status": "ok",
                "environment": args.environment,
            },
        )

        await publisher.publish(envelope)

        print(
            json.dumps(
                {
                    "published": True,
                    "topic": HEARTBEAT_TOPIC,
                    "event_id": str(envelope.event_id),
                }
            )
        )
    finally:
        await producer.close()


def cmd_publish_heartbeat(args: argparse.Namespace) -> int:
    asyncio.run(publish_heartbeat(args))
    return 0


def decode_headers(raw_headers: list[tuple[str, bytes]] | None) -> dict[str, str]:
    headers: dict[str, str] = {}

    if not raw_headers:
        return headers

    for key, value in raw_headers:
        headers[key] = value.decode("utf-8", errors="replace")

    return headers


async def consume_heartbeat(args: argparse.Namespace) -> int:
    consumer = AIOKafkaConsumer(
        HEARTBEAT_TOPIC,
        bootstrap_servers=args.bootstrap_servers,
        group_id=args.group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )

    await consumer.start()

    received = 0

    try:
        deadline = asyncio.get_event_loop().time() + args.timeout_seconds

        while received < args.max_messages:
            remaining = deadline - asyncio.get_event_loop().time()

            if remaining <= 0:
                break

            try:
                message = await asyncio.wait_for(consumer.getone(), timeout=remaining)
            except asyncio.TimeoutError:
                break

            if message is None:
                break

            consumed = ConsumedMessage(
                topic=message.topic,
                partition=message.partition,
                offset=message.offset,
                key=message.key.decode("utf-8") if message.key else None,
                value=message.value,
                headers=decode_headers(message.headers),
            )

            envelope = EventEnvelope.model_validate_json(consumed.value)

            print(envelope.model_dump_json(indent=2))

            await consumer.commit()
            received += 1
    finally:
        await consumer.stop()

    if received == 0:
        return 1

    return 0


def cmd_consume_heartbeat(args: argparse.Namespace) -> int:
    return asyncio.run(consume_heartbeat(args))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="apexquant-event-bus",
        description="ApexQuant Ultra event bus infrastructure tooling",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap")
    add_bootstrap_arguments(bootstrap_parser)
    bootstrap_parser.set_defaults(func=cmd_bootstrap)

    verify_parser = subparsers.add_parser("verify")
    add_bootstrap_arguments(verify_parser)
    verify_parser.set_defaults(func=cmd_verify)

    publish_parser = subparsers.add_parser("publish-heartbeat")
    add_bootstrap_arguments(publish_parser)
    publish_parser.add_argument("--service-name", required=True)
    publish_parser.add_argument("--plane", required=True)
    publish_parser.set_defaults(func=cmd_publish_heartbeat)

    consume_parser = subparsers.add_parser("consume-heartbeat")
    add_bootstrap_arguments(consume_parser)
    consume_parser.add_argument("--group-id", default="apexquant-event-bus-verifier")
    consume_parser.add_argument("--max-messages", type=int, default=1)
    consume_parser.add_argument("--timeout-seconds", type=float, default=10.0)
    consume_parser.set_defaults(func=cmd_consume_heartbeat)

    args = parser.parse_args(argv)

    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"event bus operation failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())