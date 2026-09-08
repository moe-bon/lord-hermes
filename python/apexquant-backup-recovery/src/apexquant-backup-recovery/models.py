from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> UUID:
    return uuid4()


class TargetSystem(str, Enum):
    POSTGRES = "POSTGRES"
    CLICKHOUSE = "CLICKHOUSE"
    OBJECT_STORAGE = "OBJECT_STORAGE"
    REDIS = "REDIS"


class BackupRunStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ArtifactStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    DELETED = "DELETED"


class RestoreStatus(str, Enum):
    DRY_RUN = "DRY_RUN"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class BackupPolicy(BaseModel):
    policy_id: UUID | None = None
    name: str
    target_system: TargetSystem
    target_name: str
    target_connection_ref: str
    storage_bucket: str
    storage_prefix: str = "backups/"
    interval_minutes: int = Field(default=1440, gt=0)
    backup_timeout_seconds: int = Field(default=3600, gt=0)
    retention_count: int | None = Field(default=None, gt=0)
    retention_days: int | None = Field(default=None, gt=0)
    delete_expired: bool = False
    encryption_key_ref: str | None = None
    enabled: bool = True
    next_run_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BackupRun(BaseModel):
    run_id: UUID | None = None
    policy_id: UUID
    trigger: str = "manual"
    status: BackupRunStatus = BackupRunStatus.RUNNING
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    artifact_uri: str | None = None
    artifact_size_bytes: int | None = None
    checksum_sha256: str | None = None
    error: str | None = None
    verification_status: str | None = None
    last_verified_at: datetime | None = None


class BackupArtifact(BaseModel):
    artifact_id: UUID | None = None
    run_id: UUID
    policy_id: UUID
    target_system: TargetSystem
    target_name: str
    storage_key: str
    uri: str
    size_bytes: int = Field(ge=0)
    checksum_sha256: str
    encryption_key_ref: str | None = None
    status: ArtifactStatus = ArtifactStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None


class RestoreRun(BaseModel):
    restore_id: UUID | None = None
    backup_run_id: UUID
    target_connection_ref: str
    target_connection_redacted: str
    command_redacted: str | None = None
    status: RestoreStatus = RestoreStatus.DRY_RUN
    dry_run: bool = True
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    error: str | None = None