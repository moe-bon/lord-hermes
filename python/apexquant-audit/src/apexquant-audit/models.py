from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from apexquant_audit.hashing import AuditFields


class ActorType(str, Enum):
    SERVICE = "SERVICE"
    USER = "USER"
    SYSTEM = "SYSTEM"


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    INFO = "INFO"


class Severity(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_timestamp(value: datetime | None) -> datetime:
    if value is None:
        return utc_now()

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


class AuditEventRequest(BaseModel):
    event_id: UUID | None = None
    occurred_at: datetime | None = None

    actor_type: ActorType
    actor_id: str | None = None
    principal_name: str | None = None

    service_name: str
    plane: str

    action: str
    resource_type: str = ""
    resource_id: str = ""

    decision: Decision = Decision.INFO
    reason: str = ""
    severity: Severity = Severity.INFO

    request_id: str | None = None
    correlation_id: str | None = None
    trace_id: str | None = None
    idempotency_key: str | None = None

    data: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def enforce_audit_policy(self) -> AuditEventRequest:
        if not self.service_name.strip():
            raise ValueError("service_name must not be empty")

        if not self.plane.strip():
            raise ValueError("plane must not be empty")

        if not self.action.strip():
            raise ValueError("action must not be empty")

        return self

    def to_fields(self) -> AuditFields:
        return AuditFields(
            event_id=self.event_id or uuid4(),
            occurred_at=normalize_timestamp(self.occurred_at),
            actor_type=self.actor_type.value,
            actor_id=self.actor_id,
            principal_name=self.principal_name,
            service_name=self.service_name.strip(),
            plane=self.plane.strip(),
            action=self.action.strip(),
            resource_type=self.resource_type.strip(),
            resource_id=self.resource_id.strip(),
            decision=self.decision.value,
            reason=self.reason,
            severity=self.severity.value,
            request_id=self.request_id,
            correlation_id=self.correlation_id,
            trace_id=self.trace_id,
            idempotency_key=self.idempotency_key,
            data=self.data,
        )


class AuditEventRecord(BaseModel):
    event_seq: int
    event_id: UUID
    occurred_at: datetime
    event_hash: str