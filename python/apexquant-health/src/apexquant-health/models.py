from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class DependencyStatus(BaseModel):
    status: HealthStatus
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: HealthStatus
    service: str
    version: str
    plane: str
    environment: str
    instance_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    dependencies: dict[str, DependencyStatus] = Field(default_factory=dict)