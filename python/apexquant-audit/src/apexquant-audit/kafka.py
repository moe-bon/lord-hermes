from __future__ import annotations

import json
from typing import Any

from aiokafka import AIOKafkaProducer


class AuditKafkaPublisher:
    def __init__(self, bootstrap_servers: str | None, topic: str) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._producer: AIOKafkaProducer | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._bootstrap_servers)

    async def start(self) -> None:
        if not self.enabled:
            return

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            acks="all",
            enable_idempotence=True,
        )
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish(self, row: dict[str, Any]) -> tuple[bool, str | None]:
        if not self.enabled or self._producer is None:
            return False, "publisher disabled"

        try:
            payload = {
                "event_seq": row["event_seq"],
                "event_id": str(row["event_id"]),
                "occurred_at": row["occurred_at"].isoformat(),
                "actor_type": row["actor_type"],
                "actor_id": row["actor_id"],
                "principal_name": row["principal_name"],
                "service_name": row["service_name"],
                "plane": row["plane"],
                "action": row["action"],
                "resource_type": row["resource_type"],
                "resource_id": row["resource_id"],
                "decision": row["decision"],
                "reason": row["reason"],
                "severity": row["severity"],
                "request_id": row["request_id"],
                "correlation_id": row["correlation_id"],
                "trace_id": row["trace_id"],
                "idempotency_key": row["idempotency_key"],
                "data": row["data"],
                "prev_hash": row["prev_hash"],
                "event_hash": row["event_hash"],
            }

            headers = [
                ("event_id", str(row["event_id"]).encode("utf-8")),
                ("service_name", row["service_name"].encode("utf-8")),
                ("action", row["action"].encode("utf-8")),
                ("event_hash", row["event_hash"].encode("utf-8")),
            ]

            await self._producer.send_and_wait(
                self._topic,
                value=json.dumps(payload, default=str).encode("utf-8"),
                key=str(row["event_id"]).encode("utf-8"),
                headers=headers,
            )

            return True, None
        except Exception as exc:
            return False, str(exc)