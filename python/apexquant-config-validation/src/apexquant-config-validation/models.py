from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class ValidationIssue(BaseModel):
    severity: Severity
    path: str
    message: str


class ValidationReport(BaseModel):
    schema_key: str
    ok: bool
    config_hash: str | None = None
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)