from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

GENESIS_HASH = "0" * 64
AUDIT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class AuditFields:
    event_id: UUID
    occurred_at: datetime
    actor_type: str
    actor_id: str | None
    principal_name: str | None
    service_name: str
    plane: str
    action: str
    resource_type: str
    resource_id: str
    decision: str
    reason: str
    severity: str
    request_id: str | None
    correlation_id: str | None
    trace_id: str | None
    idempotency_key: str | None
    data: dict


def format_timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def canonical_payload(fields: AuditFields, prev_hash: str) -> dict[str, Any]:
    return {
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "event_id": str(fields.event_id),
        "occurred_at": format_timestamp(fields.occurred_at),
        "actor_type": fields.actor_type,
        "actor_id": fields.actor_id,
        "principal_name": fields.principal_name,
        "service_name": fields.service_name,
        "plane": fields.plane,
        "action": fields.action,
        "resource_type": fields.resource_type,
        "resource_id": fields.resource_id,
        "decision": fields.decision,
        "reason": fields.reason,
        "severity": fields.severity,
        "request_id": fields.request_id,
        "correlation_id": fields.correlation_id,
        "trace_id": fields.trace_id,
        "idempotency_key": fields.idempotency_key,
        "data": fields.data,
        "prev_hash": prev_hash,
    }


def compute_event_hash(fields: AuditFields, prev_hash: str) -> str:
    payload = canonical_payload(fields, prev_hash)

    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )

    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def fields_from_row(row: dict[str, Any]) -> AuditFields:
    return AuditFields(
        event_id=row["event_id"],
        occurred_at=row["occurred_at"],
        actor_type=row["actor_type"],
        actor_id=row["actor_id"],
        principal_name=row["principal_name"],
        service_name=row["service_name"],
        plane=row["plane"],
        action=row["action"],
        resource_type=row["resource_type"],
        resource_id=row["resource_id"],
        decision=row["decision"],
        reason=row["reason"],
        severity=row["severity"],
        request_id=row["request_id"],
        correlation_id=row["correlation_id"],
        trace_id=row["trace_id"],
        idempotency_key=row["idempotency_key"],
        data=row["data"],
    )


def verify_chain(rows: list[dict[str, Any]], initial_prev_hash: str) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    prev_hash = initial_prev_hash
    expected_seq: int | None = None

    for row in rows:
        if expected_seq is None:
            expected_seq = int(row["event_seq"])

        if int(row["event_seq"]) != expected_seq:
            violations.append(
                {
                    "event_seq": row["event_seq"],
                    "type": "SEQUENCE_GAP",
                    "detail": f"expected {expected_seq}, found {row['event_seq']}",
                }
            )

        if row["prev_hash"] != prev_hash:
            violations.append(
                {
                    "event_seq": row["event_seq"],
                    "type": "PREV_HASH_MISMATCH",
                    "detail": "previous hash does not match expected chain value",
                }
            )

        fields = fields_from_row(row)
        expected_hash = compute_event_hash(fields, prev_hash)

        if row["event_hash"] != expected_hash:
            violations.append(
                {
                    "event_seq": row["event_seq"],
                    "type": "EVENT_HASH_MISMATCH",
                    "detail": "event hash does not match canonical recomputation",
                }
            )

        prev_hash = row["event_hash"]
        expected_seq = (expected_seq or int(row["event_seq"])) + 1

    return {
        "ok": len(violations) == 0,
        "events_checked": len(rows),
        "violations": violations,
    }