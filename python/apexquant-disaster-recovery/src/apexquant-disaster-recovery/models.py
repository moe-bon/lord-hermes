from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> UUID:
    return uuid4()


class PlanStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class ComponentType(str, Enum):
    SERVICE = "SERVICE"
    DATABASE = "DATABASE"
    EVENT_BUS = "EVENT_BUS"
    OBJECT_STORAGE = "OBJECT_STORAGE"
    REDIS = "REDIS"
    CONFIG = "CONFIG"


class RecoveryStrategy(str, Enum):
    RESTORE_FROM_BACKUP = "RESTORE_FROM_BACKUP"
    RESTART = "RESTART"
    REBUILD = "REBUILD"
    FAILOVER = "FAILOVER"
    MANUAL = "MANUAL"


class DrillStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class RecoveryPlan(BaseModel):
    plan_id: UUID | None = None
    name: str
    environment: str
    description: str = ""
    criticality_tier: str = "TIER_1"
    rpo_seconds: int = Field(gt=0)
    rto_seconds: int = Field(gt=0)
    drill_max_age_days: int | None = Field(default=7, gt=0)
    status: PlanStatus = PlanStatus.DRAFT
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RecoveryComponent(BaseModel):
    component_id: UUID | None = None
    plan_id: UUID | None = None
    component_name: str
    component_type: ComponentType
    recovery_strategy: RecoveryStrategy
    priority: int = Field(default=100, gt=0)
    backup_policy_name: str | None = None
    health_endpoint: str | None = None
    rpo_seconds: int | None = Field(default=None, gt=0)
    rto_seconds: int | None = Field(default=None, gt=0)
    notes: str = ""


class DrillStep(BaseModel):
    step_id: UUID | None = None
    drill_id: UUID | None = None
    step_name: str
    step_order: int
    status: StepStatus = StepStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict = Field(default_factory=dict)
    error: str | None = None


class Drill(BaseModel):
    drill_id: UUID | None = None
    plan_id: UUID
    environment: str
    trigger: str = "manual"
    actor: str = "system"
    status: DrillStatus = DrillStatus.RUNNING
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    readiness_score: float | None = Field(default=None, ge=0, le=100)
    result: dict = Field(default_factory=dict)
    error: str | None = None


class DREvent(BaseModel):
    event_id: UUID | None = None
    plan_id: UUID | None = None
    drill_id: UUID | None = None
    event_type: str
    severity: str = "INFO"
    actor: str = "system"
    reason: str = ""
    details: dict = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=utc_now)


class BackupStatus(BaseModel):
    policy_name: str
    latest_success_at: datetime | None = None
    latest_artifact_uri: str | None = None
    verification_status: str | None = None
    last_verified_at: datetime | None = None


class BackupRequirementStatus(BaseModel):
    component_name: str
    backup_policy_name: str | None = None
    required: bool = False
    policy_exists: bool = False
    latest_backup_at: datetime | None = None
    fresh: bool = False
    verified: bool = False
    rpo_seconds: int | None = None


class HealthCheckStatus(BaseModel):
    component_name: str
    health_endpoint: str | None = None
    applicable: bool = False
    checked: bool = False
    healthy: bool | None = None


class ReadinessReport(BaseModel):
    plan_id: UUID
    environment: str
    computed_at: datetime = Field(default_factory=utc_now)
    plan_active: bool = False
    score: float = Field(default=0.0, ge=0, le=100)
    state: str = "NOT_READY"
    fail_closed_triggered: bool = False
    backup_requirements: list[BackupRequirementStatus] = Field(default_factory=list)
    health_checks: list[HealthCheckStatus] = Field(default_factory=list)
    recent_drill_passed: bool = False
    warnings: list[str] = Field(default_factory=list)