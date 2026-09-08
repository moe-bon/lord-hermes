from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class PrincipalType(str, Enum):
    SERVICE = "SERVICE"
    ADMIN = "ADMIN"
    USER = "USER"


class CredentialStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class Principal(BaseModel):
    principal_id: str
    subject_name: str
    principal_type: PrincipalType
    display_name: str = ""
    active: bool = True


class CredentialRecord(BaseModel):
    credential_id: str
    principal_id: str
    identifier: str
    status: CredentialStatus
    expires_at: datetime | None = None
    last_used_at: datetime | None = None


class TokenClaims(BaseModel):
    sub: str
    typ: str
    iat: int
    exp: int
    jti: str
    permissions: list[str] = Field(default_factory=list)


class AuthContext(BaseModel):
    subject: str
    principal_type: str
    permissions: list[str] = Field(default_factory=list)
    expires_at: int
    jti: str


class IssueTokenRequest(BaseModel):
    api_key: str
    ttl_seconds: int = Field(default=300, ge=30, le=3600)


class IssueTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    permissions: list[str]


class CreateApiKeyRequest(BaseModel):
    subject_name: str
    principal_type: PrincipalType
    permissions: list[str] = Field(default_factory=list)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class CreateApiKeyResponse(BaseModel):
    subject_name: str
    principal_type: PrincipalType
    identifier: str
    api_key: str
    permissions: list[str]


class RevokeApiKeyRequest(BaseModel):
    identifier: str


class AuthorizeRequest(BaseModel):
    action: str
    resource: str


class AuthorizeResponse(BaseModel):
    allowed: bool
    reason: str