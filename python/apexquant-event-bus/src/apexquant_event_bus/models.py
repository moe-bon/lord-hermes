from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

EVENT_TYPE_PATTERN = re.compile(
    r"^[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[a-z0-9]+(?:-[a-z0-9]+)*){2,}$"
)

TOPIC_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")


def validate_event_type(value: str) -> None:
    if not value.strip():
        raise ValueError("event_type must not be empty")

    if len(value) > 249:
        raise ValueError("event_type must not exceed 249 characters")

    if not EVENT_TYPE_PATTERN.match(value):
        raise ValueError(
            "event_type must be lowercase dot-separated segments, "
            "for example platform.event-bus.heartbeat"
        )


def validate_topic_name(value: str) -> None:
    if not value.strip():
        raise ValueError("topic name must not be empty")

    if len(value) > 249:
        raise ValueError("topic name must not exceed 249 characters")

    if not TOPIC_NAME_PATTERN.match(value):
        raise ValueError(
            "topic name may only contain letters, numbers, dots, hyphens, and underscores"
        )

    if value.startswith(".") or value.endswith("."):
        raise ValueError("topic name must not start or end with a dot")


class EventEnvelope(BaseModel):
    event_id: UUID
    event_type: str
    event_version: int = Field(ge=1)
    occurred_at: datetime
    producer_service: str
    producer_plane: str
    correlation_id: UUID | None = None
    causation_id: UUID | None = None
    idempotency_key: str
    trace_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def enforce_event_policy(self) -> EventEnvelope:
        validate_event_type(self.event_type)

        if not self.idempotency_key.strip():
            raise ValueError("idempotency_key must not be empty")

        if not self.producer_service.strip():
            raise ValueError("producer_service must not be empty")

        if not self.producer_plane.strip():
            raise ValueError("producer_plane must not be empty")

        if self.occurred_at.tzinfo is None:
            self.occurred_at = self.occurred_at.replace(tzinfo=timezone.utc)

        return self

    @property
    def topic(self) -> str:
        return f"{self.event_type}.v{self.event_version}"


class TopicSpec(BaseModel):
    name: str
    domain: str
    description: str = ""
    partitions: int = Field(ge=1)
    replication_factor: int = Field(ge=1)
    retention_ms: int = Field(ge=0)
    cleanup_policy: str = "delete"

    @model_validator(mode="after")
    def enforce_topic_policy(self) -> TopicSpec:
        validate_topic_name(self.name)

        if not self.domain.strip():
            raise ValueError("topic domain must not be empty")

        if self.cleanup_policy not in {"delete", "compact"}:
            raise ValueError("cleanup_policy must be delete or compact")

        return self


class ConsumedMessage(BaseModel):
    topic: str
    partition: int
    offset: int
    key: str | None = None
    value: bytes
    headers: dict[str, str] = Field(default_factory=dict)


class EventBusVerificationReport(BaseModel):
    environment: str
    bootstrap_servers: str
    generated_at: datetime
    ok: bool
    missing_topics: list[str] = Field(default_factory=list)
    observed_topics: list[str] = Field(default_factory=list)