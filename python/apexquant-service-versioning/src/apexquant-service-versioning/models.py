from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class LifecycleStatus(str, Enum):
    DRAFT = "DRAFT"
    RELEASED = "RELEASED"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"


class ServiceCreate(BaseModel):
    service_name: str = Field(pattern=r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$")
    plane: str = Field(min_length=1)
    description: str = ""


class ServiceInfo(BaseModel):
    service_name: str
    plane: str
    description: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DependencySpec(BaseModel):
    service_name: str = Field(pattern=r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$")
    min_version: str = Field(min_length=5)


class VersionCreate(BaseModel):
    version: str = Field(min_length=5)
    git_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{7,40}$")
    image_tag: str | None = None
    api_version: str = "v1"
    min_compatible_version: str | None = None
    dependencies: list[DependencySpec] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ReleaseRequest(BaseModel):
    git_sha: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    image_tag: str = Field(min_length=1)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    actor: str = Field(min_length=1)
    reason: str = ""


class ActorRequest(BaseModel):
    actor: str = Field(min_length=1)
    reason: str = ""


class ServiceVersion(BaseModel):
    version_id: str
    service_name: str
    version: str
    status: LifecycleStatus
    git_sha: str | None = None
    image_tag: str | None = None
    api_version: str
    min_compatible_version: str | None = None
    checksum_sha256: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None
    released_at: datetime | None = None
    deprecated_at: datetime | None = None
    retired_at: datetime | None = None
    dependencies: list[DependencySpec] = Field(default_factory=list)


class CompatibilityDependencyReport(BaseModel):
    service_name: str
    min_version: str
    resolved_version: str | None = None
    compatible: bool
    reason: str = ""


class CompatibilityReport(BaseModel):
    service_name: str
    version: str
    ok: bool
    dependencies: list[CompatibilityDependencyReport] = Field(default_factory=list)