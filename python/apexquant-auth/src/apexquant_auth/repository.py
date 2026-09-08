from __future__ import annotations

from datetime import datetime

from psycopg_pool import ConnectionPool

from apexquant_auth.models import PrincipalType
from apexquant_auth.security import hash_api_key_secret, parse_api_key


class PostgresAuthRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def ensure_bootstrap(
        self,
        subject_name: str,
        principal_type: PrincipalType,
        permissions: list[str],
        api_key: str,
    ) -> None:
        identifier, secret = parse_api_key(api_key)
        secret_hash = hash_api_key_secret(secret)

        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO auth.principals (
                    subject_name,
                    principal_type,
                    display_name,
                    active
                )
                VALUES (
                    %s,
                    %s::auth.principal_type,
                    %s,
                    TRUE
                )
                ON CONFLICT (subject_name) DO UPDATE SET
                    principal_type = EXCLUDED.principal_type,
                    active = TRUE,
                    updated_at = now()
                RETURNING principal_id
                """,
                (subject_name, principal_type.value, subject_name),
            ).fetchone()

            principal_id = row[0]

            for permission in permissions:
                conn.execute(
                    """
                    INSERT INTO auth.permission_grants (
                        principal_id,
                        permission
                    )
                    VALUES (
                        %s,
                        %s
                    )
                    ON CONFLICT (principal_id, permission) DO NOTHING
                    """,
                    (principal_id, permission),
                )

            conn.execute(
                """
                INSERT INTO auth.credentials (
                    principal_id,
                    credential_type,
                    identifier,
                    secret_hash,
                    status
                )
                VALUES (
                    %s,
                    'API_KEY'::auth.credential_type,
                    %s,
                    %s,
                    'ACTIVE'::auth.credential_status
                )
                ON CONFLICT (identifier) DO UPDATE SET
                    principal_id = EXCLUDED.principal_id,
                    secret_hash = EXCLUDED.secret_hash,
                    status = 'ACTIVE'::auth.credential_status,
                    expires_at = NULL,
                    updated_at = now()
                """,
                (principal_id, identifier, secret_hash),
            )

    def get_credential_with_principal(self, identifier: str) -> dict | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    c.credential_id,
                    c.principal_id,
                    c.identifier,
                    c.secret_hash,
                    c.status::text AS credential_status,
                    c.expires_at,
                    c.last_used_at,
                    p.subject_name,
                    p.principal_type::text AS principal_type,
                    p.active AS principal_active
                FROM auth.credentials c
                JOIN auth.principals p ON p.principal_id = c.principal_id
                WHERE c.identifier = %s
                """,
                (identifier,),
            ).fetchone()

            if row is None:
                return None

            return {
                "credential_id": row[0],
                "principal_id": row[1],
                "identifier": row[2],
                "secret_hash": row[3],
                "credential_status": row[4],
                "expires_at": row[5],
                "last_used_at": row[6],
                "subject_name": row[7],
                "principal_type": row[8],
                "principal_active": row[9],
            }

    def get_permissions(self, principal_id: str) -> list[str]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT permission
                FROM auth.permission_grants
                WHERE principal_id = %s
                  AND (expires_at IS NULL OR expires_at > now())
                ORDER BY permission
                """,
                (principal_id,),
            ).fetchall()

            return [row[0] for row in rows]

    def update_last_used(self, credential_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE auth.credentials
                SET last_used_at = now()
                WHERE credential_id = %s
                """,
                (credential_id,),
            )

    def create_principal(
        self,
        subject_name: str,
        principal_type: PrincipalType,
    ) -> str:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO auth.principals (
                    subject_name,
                    principal_type,
                    display_name,
                    active
                )
                VALUES (
                    %s,
                    %s::auth.principal_type,
                    %s,
                    TRUE
                )
                ON CONFLICT (subject_name) DO UPDATE SET
                    principal_type = EXCLUDED.principal_type,
                    active = TRUE,
                    updated_at = now()
                RETURNING principal_id
                """,
                (subject_name, principal_type.value, subject_name),
            ).fetchone()

            return str(row[0])

    def grant_permissions(self, principal_id: str, permissions: list[str]) -> None:
        with self._pool.connection() as conn:
            for permission in permissions:
                conn.execute(
                    """
                    INSERT INTO auth.permission_grants (
                        principal_id,
                        permission
                    )
                    VALUES (
                        %s,
                        %s
                    )
                    ON CONFLICT (principal_id, permission) DO NOTHING
                    """,
                    (principal_id, permission),
                )

    def create_credential(
        self,
        principal_id: str,
        identifier: str,
        secret_hash: str,
        expires_at: datetime | None = None,
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO auth.credentials (
                    principal_id,
                    credential_type,
                    identifier,
                    secret_hash,
                    status,
                    expires_at
                )
                VALUES (
                    %s,
                    'API_KEY'::auth.credential_type,
                    %s,
                    %s,
                    'ACTIVE'::auth.credential_status,
                    %s
                )
                """,
                (principal_id, identifier, secret_hash, expires_at),
            )

    def revoke_credential(self, identifier: str) -> bool:
        with self._pool.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE auth.credentials
                SET status = 'REVOKED'::auth.credential_status
                WHERE identifier = %s
                """,
                (identifier,),
            )

            return cursor.rowcount > 0

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
        import json

        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO auth.auth_events (
                    subject_name,
                    principal_type,
                    action,
                    decision,
                    reason,
                    request_id,
                    details
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    subject_name,
                    principal_type,
                    action,
                    decision,
                    reason,
                    request_id,
                    json.dumps(details or {}),
                ),
            )