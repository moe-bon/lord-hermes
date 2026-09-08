from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class PathKind(str, Enum):
    DIR = "DIR"
    FILE = "FILE"


class RequiredPath(BaseModel):
    path: str
    kind: PathKind
    description: str


class Violation(BaseModel):
    code: str
    severity: Severity
    path: str
    message: str


class VerificationReport(BaseModel):
    repo_root: str
    started_at: datetime
    completed_at: datetime
    ok: bool
    errors_count: int = Field(default=0, ge=0)
    warnings_count: int = Field(default=0, ge=0)
    violations: list[Violation] = Field(default_factory=list)
    checked_paths: list[str] = Field(default_factory=list)
    cargo_members: list[str] = Field(default_factory=list)
    python_packages: list[str] = Field(default_factory=list)