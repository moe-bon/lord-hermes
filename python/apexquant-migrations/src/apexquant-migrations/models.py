from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class MigrationEngine(str, Enum):
    POSTGRES = "postgres"
    CLICKHOUSE = "clickhouse"


class MigrationFile(BaseModel):
    engine: MigrationEngine
    domain: str
    filename: str
    path: str
    version: str
    migration_id: str
    checksum_sha256: str


class AppliedMigration(BaseModel):
    migration_id: str
    engine: MigrationEngine
    domain: str
    version: str
    filename: str
    checksum_sha256: str
    applied_at: datetime


class MigrationPlan(BaseModel):
    engine: MigrationEngine
    ok: bool
    pending: list[MigrationFile] = Field(default_factory=list)
    applied: list[AppliedMigration] = Field(default_factory=list)
    drift: list[dict] = Field(default_factory=list)


class MigrationRunReport(BaseModel):
    engine: MigrationEngine
    mode: str
    started_at: datetime
    completed_at: datetime
    ok: bool
    planned: int = Field(default=0, ge=0)
    applied: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    error: str | None = None
    details: list[dict] = Field(default_factory=list)