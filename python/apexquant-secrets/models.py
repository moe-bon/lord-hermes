from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SecretClassification(str, Enum):
    INFRASTRUCTURE = "INFRASTRUCTURE"
    DATABASE = "DATABASE"
    BROKER = "BROKER"
    EXECUTION = "EXECUTION"
    API = "API"
    MODEL = "MODEL"
    KNOWLEDGE = "KNOWLEDGE"
    OBSERVABILITY = "OBSERVABILITY"


class SecretPlane(str, Enum):
    CONTROL = "CONTROL"
    MARKET_DATA = "MARKET_DATA"
    TRADING = "TRADING"
    RISK = "RISK"
    AI = "AI"
    DATA_RESEARCH = "DATA_RESEARCH"
    OBSERVABILITY = "OBSERVABILITY"


class SecretAction(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    ROTATE = "ROTATE"
    ADMIN = "ADMIN"


class PolicyEffect(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class SecretVersionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class PolicyRule(BaseModel):
    subject_plane: SecretPlane | None = None
    classification: SecretClassification | None = None
    action: SecretAction | None = None
    effect: PolicyEffect


class PolicyEvaluation(BaseModel):
    allowed: bool
    reason: str
    matched_rules: list[PolicyRule] = Field(default_factory=list)


class SecretVersion(BaseModel):
    version: int = Field(ge=1)
    value: str
    status: SecretVersionStatus
    created_at: datetime


class SecretEntry(BaseModel):
    classification: SecretClassification
    description: str = ""
    current_version: int = Field(default=0, ge=0)
    versions: list[SecretVersion] = Field(default_factory=list)


class SecretMetadata(BaseModel):
    name: str
    classification: SecretClassification
    description: str = ""
    current_version: int = Field(default=0, ge=0)


class SecretStorePayload(BaseModel):
    secrets: dict[str, SecretEntry] = Field(default_factory=dict)


class AuditEvent(BaseModel):
    occurred_at: datetime
    request_id: str
    subject_service_name: str
    subject_plane: SecretPlane
    secret_name: str
    action: SecretAction
    decision: PolicyEffect
    reason: str = ""