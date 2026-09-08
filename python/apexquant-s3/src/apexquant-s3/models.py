from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class BucketPurpose(str, Enum):
    MARKET_DATA_RAW = "MARKET_DATA_RAW"
    MODEL_ARTIFACTS = "MODEL_ARTIFACTS"
    KNOWLEDGE_RAW = "KNOWLEDGE_RAW"
    BACKUPS = "BACKUPS"
    TEMPORARY = "TEMPORARY"


class BucketSpec(BaseModel):
    name: str
    purpose: BucketPurpose
    versioning_enabled: bool = False
    lifecycle_expiration_days: int | None = None

    @model_validator(mode="after")
    def enforce_bucket_policy(self) -> BucketSpec:
        if not self.name.strip():
            raise ValueError("bucket name must not be empty")

        if self.purpose == BucketPurpose.MODEL_ARTIFACTS and not self.versioning_enabled:
            raise ValueError("model artifact buckets must have versioning enabled")

        if self.purpose == BucketPurpose.KNOWLEDGE_RAW and not self.versioning_enabled:
            raise ValueError("knowledge raw buckets must have versioning enabled")

        if self.purpose == BucketPurpose.TEMPORARY and self.lifecycle_expiration_days is None:
            raise ValueError("temporary buckets must have a lifecycle expiration policy")

        return self


class ObjectReference(BaseModel):
    bucket_name: str
    object_key: str
    version_id: str | None = None
    content_type: str
    size_bytes: int = Field(ge=0)
    checksum_sha256: str | None = None