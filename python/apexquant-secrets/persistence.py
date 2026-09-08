from __future__ import annotations

from typing import Any, Protocol, Sequence

from apexquant_secrets.models import (
    AuditEvent,
    PolicyEffect,
    PolicyRule,
    SecretAction,
    SecretClassification,
    SecretPlane,
)


class DatabaseConnection(Protocol):
    def execute(
        self,
        query: str,
        parameters: Sequence[Any] | None = None,
        /,
    ) -> Any:
        raise NotImplementedError

    def commit(self) -> None:
        raise NotImplementedError


def persist_secret_metadata(
    connection: DatabaseConnection,
    name: str,
    classification: SecretClassification,
    description: str,
    current_version: int,
) -> None:
    connection.execute(
        """
        INSERT INTO secrets_management.secret_metadata (
            name,
            classification,
            description,
            current_version
        )
        VALUES (
            %s,
            %s,
            %s,
            %s
        )
        ON CONFLICT (name) DO UPDATE SET
            classification = EXCLUDED.classification,
            description = EXCLUDED.description,
            current_version = EXCLUDED.current_version
        """,
        (
            name,
            classification.value,
            description,
            current_version,
        ),
    )

    connection.commit()


def persist_secret_version(
    connection: DatabaseConnection,
    name: str,
    version: int,
) -> None:
    row = connection.execute(
        """
        SELECT secret_id
        FROM secrets_management.secret_metadata
        WHERE name = %s
        """,
        (name,),
    ).fetchone()

    if row is None:
        raise ValueError(f"secret metadata does not exist: {name}")

    secret_id = row[0]

    connection.execute(
        """
        INSERT INTO secrets_management.secret_versions (
            secret_id,
            version,
            status
        )
        VALUES (
            %s,
            %s,
            'ACTIVE'
        )
        ON CONFLICT (secret_id, version) DO UPDATE SET
            status = 'ACTIVE'
        """,
        (
            secret_id,
            version,
        ),
    )

    connection.commit()


def persist_audit_event(
    connection: DatabaseConnection,
    event: AuditEvent,
) -> None:
    connection.execute(
        """
        INSERT INTO secrets_management.secret_access_audit (
            occurred_at,
            request_id,
            subject_service_name,
            subject_plane,
            secret_name,
            action,
            decision,
            reason
        )
        VALUES (
            %s,
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
            event.occurred_at,
            event.request_id,
            event.subject_service_name,
            event.subject_plane.value,
            event.secret_name,
            event.action.value,
            event.decision.value,
            event.reason,
        ),
    )


def load_policy_rules(connection: DatabaseConnection) -> list[PolicyRule]:
    rows = connection.execute(
        """
        SELECT
            subject_plane,
            classification,
            action,
            effect
        FROM secrets_management.secret_access_policies
        ORDER BY priority DESC, created_at ASC
        """
    ).fetchall()

    rules: list[PolicyRule] = []

    for row in rows:
        subject_plane_raw, classification_raw, action_raw, effect_raw = row

        subject_plane = None
        classification = None
        action = None

        if subject_plane_raw and subject_plane_raw != "*":
            subject_plane = SecretPlane(subject_plane_raw)

        if classification_raw and classification_raw != "*":
            classification = SecretClassification(classification_raw)

        if action_raw and action_raw != "*":
            action = SecretAction(action_raw)

        rules.append(
            PolicyRule(
                subject_plane=subject_plane,
                classification=classification,
                action=action,
                effect=PolicyEffect(effect_raw),
            )
        )

    return rules