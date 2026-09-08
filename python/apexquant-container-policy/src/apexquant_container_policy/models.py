from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class Violation(BaseModel):
    service_name: str
    code: str
    severity: Severity
    message: str


class VerificationReport(BaseModel):
    compose_path: str
    started_at: datetime
    completed_at: datetime
    ok: bool
    errors_count: int = Field(default=0, ge=0)
    warnings_count: int = Field(default=0, ge=0)
    services_checked: list[str] = Field(default_factory=list)
    violations: list[Violation] = Field(default_factory=list)