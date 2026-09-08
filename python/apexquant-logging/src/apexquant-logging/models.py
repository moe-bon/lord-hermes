from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LogEnvelope(BaseModel):
    ts: datetime = Field(default_factory=utc_now)
    level: LogLevel
    service: str
    service_version: str = "unknown"
    environment: str
    plane: str
    event: str
    message: str

    trace_id: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    actor_id: str | None = None

    data: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def enforce_logging_policy(self) -> LogEnvelope:
        if not self.service.strip():
            raise ValueError("service must not be empty")

        if not self.environment.strip():
            raise ValueError("environment must not be empty")

        if not self.plane.strip():
            raise ValueError("plane must not be empty")

        if not self.event.strip():
            raise ValueError("event must not be empty")

        if self.ts.tzinfo is None:
            self.ts = self.ts.replace(tzinfo=timezone.utc)

        return self