from __future__ import annotations

import time
import uuid
from typing import Protocol

from apexquant_auth.models import (
    AuthContext,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    IssueTokenResponse,
    PrincipalType,
    TokenClaims,
)
from apexquant_auth.permissions import has_permission
from apexquant_auth.security import (
    AuthSecurityError,
    generate_api_key,
    hash_api_key_secret,
    parse_api_key,
    sign_token,
    verify_api_key_secret,
    verify_token,
)


class AuthRepository(Protocol):
    def ensure_bootstrap(
        self,
        subject_name: str,
        principal_type: PrincipalType,
        permissions: list[str],
        api_key: str,
    ) -> None:
        raise NotImplementedError

    def get_credential_with_principal(self, identifier: str) -> dict | None:
        raise NotImplementedError

    def get_permissions(self, principal_id: str) -> list[str]:
        raise NotImplementedError

    def update_last_used(self, credential_id: str) -> None:
        raise NotImplementedError

    def create_principal(
        self,
        subject_name: str,
        principal_type: PrincipalType,
    ) -> str:
        raise NotImplementedError

    def grant_permissions(self, principal_id: str, permissions: list[str]) -> None:
        raise NotImplementedError

    def create_credential(
        self,
        principal_id: str,
        identifier: str,
        secret_hash: str,
        expires_at=None,
    ) -> None:
        raise NotImplementedError

    def revoke_credential(self, identifier: str) -> bool:
        raise NotImplementedError

    def record_event(
        self,
        subject_name: str,
        principal_type: str | None,
        action: str,
        decision: str,
        reason: str,
        request_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        raise NotImplementedError


class AuthService:
    def __init__(self, repository: AuthRepository, token_secret: bytes) -> None:
        self._repository = repository
        self._token_secret = token_secret

    def ensure_bootstrap(
        self,
        subject_name: str,
        api_key: str,
        permissions: list[str],
    ) -> None:
        self._repository.ensure_bootstrap(
            subject_name=subject_name,
            principal_type=PrincipalType.ADMIN,
            permissions=permissions,
            api_key=api_key,
        )

    def issue_token(self, api_key: str, ttl_seconds: int) -> IssueTokenResponse:
        identifier, secret = parse_api_key(api_key)

        row = self._repository.get_credential_with_principal(identifier)

        if row is None:
            self._audit(
                subject_name=identifier,
                principal_type=None,
                action="ISSUE_TOKEN",
                decision="DENY",
                reason="credential not found",
            )
            raise AuthSecurityError("invalid API key")

        if row["credential_status"] != "ACTIVE":
            self._audit(
                subject_name=row["subject_name"],
                principal_type=row["principal_type"],
                action="ISSUE_TOKEN",
                decision="DENY",
                reason="credential is not active",
            )
            raise AuthSecurityError("credential is not active")

        if not row["principal_active"]:
            self._audit(
                subject_name=row["subject_name"],
                principal_type=row["principal_type"],
                action="ISSUE_TOKEN",
                decision="DENY",
                reason="principal is not active",
            )
            raise AuthSecurityError("principal is not active")

        if not verify_api_key_secret(row["secret_hash"], secret):
            self._audit(
                subject_name=row["subject_name"],
                principal_type=row["principal_type"],
                action="ISSUE_TOKEN",
                decision="DENY",
                reason="invalid API key secret",
            )
            raise AuthSecurityError("invalid API key")

        permissions = self._repository.get_permissions(row["principal_id"])
        self._repository.update_last_used(row["credential_id"])

        now = int(time.time())
        expires = now + ttl_seconds

        claims = TokenClaims(
            sub=row["subject_name"],
            typ=row["principal_type"],
            iat=now,
            exp=expires,
            jti=str(uuid.uuid4()),
            permissions=permissions,
        )

        token = sign_token(self._token_secret, claims)

        self._audit(
            subject_name=row["subject_name"],
            principal_type=row["principal_type"],
            action="ISSUE_TOKEN",
            decision="SUCCESS",
            reason="token issued",
            details={"jti": claims.jti, "ttl_seconds": ttl_seconds},
        )

        return IssueTokenResponse(
            access_token=token,
            expires_in=ttl_seconds,
            permissions=permissions,
        )

    def verify_token(self, token: str) -> AuthContext:
        now = int(time.time())

        try:
            context = verify_token(self._token_secret, token, now)
        except AuthSecurityError as exc:
            self._audit(
                subject_name="<unknown>",
                principal_type=None,
                action="VERIFY_TOKEN",
                decision="DENY",
                reason=str(exc),
            )
            raise

        self._audit(
            subject_name=context.subject,
            principal_type=context.principal_type,
            action="VERIFY_TOKEN",
            decision="SUCCESS",
            reason="token verified",
            details={"jti": context.jti},
        )

        return context

    def authorize(
        self,
        context: AuthContext,
        action: str,
        resource: str,
    ) -> bool:
        required_permission = f"{action}:{resource}"

        allowed = has_permission(context.permissions, required_permission)

        self._audit(
            subject_name=context.subject,
            principal_type=context.principal_type,
            action="AUTHORIZE",
            decision="ALLOW" if allowed else "DENY",
            reason=required_permission,
        )

        return allowed

    def create_api_key(
        self,
        caller: AuthContext,
        request: CreateApiKeyRequest,
    ) -> CreateApiKeyResponse:
        if not has_permission(caller.permissions, "auth:api_keys:write"):
            raise AuthSecurityError("caller is not authorized to create API keys")

        principal_id = self._repository.create_principal(
            subject_name=request.subject_name,
            principal_type=request.principal_type,
        )

        self._repository.grant_permissions(principal_id, request.permissions)

        identifier, secret, full_key = generate_api_key()

        expires_at = None

        if request.expires_in_days is not None:
            from datetime import datetime, timedelta, timezone

            expires_at = datetime.now(timezone.utc) + timedelta(
                days=request.expires_in_days
            )

        self._repository.create_credential(
            principal_id=principal_id,
            identifier=identifier,
            secret_hash=hash_api_key_secret(secret),
            expires_at=expires_at,
        )

        self._audit(
            subject_name=caller.subject,
            principal_type=caller.principal_type,
            action="CREATE_API_KEY",
            decision="SUCCESS",
            reason=f"created API key for {request.subject_name}",
            details={"identifier": identifier},
        )

        return CreateApiKeyResponse(
            subject_name=request.subject_name,
            principal_type=request.principal_type,
            identifier=identifier,
            api_key=full_key,
            permissions=request.permissions,
        )

    def revoke_api_key(self, caller: AuthContext, identifier: str) -> bool:
        if not has_permission(caller.permissions, "auth:api_keys:write"):
            raise AuthSecurityError("caller is not authorized to revoke API keys")

        revoked = self._repository.revoke_credential(identifier)

        self._audit(
            subject_name=caller.subject,
            principal_type=caller.principal_type,
            action="REVOKE_API_KEY",
            decision="SUCCESS" if revoked else "DENY",
            reason=f"identifier={identifier}",
        )

        return revoked

    def _audit(
        self,
        subject_name: str,
        principal_type: str | None,
        action: str,
        decision: str,
        reason: str,
        details: dict | None = None,
    ) -> None:
        self._repository.record_event(
            subject_name=subject_name,
            principal_type=principal_type,
            action=action,
            decision=decision,
            reason=reason,
            details=details or {},
        )