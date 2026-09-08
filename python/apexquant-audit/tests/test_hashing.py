from datetime import datetime, timezone
from uuid import UUID

from apexquant_audit.hashing import (
    GENESIS_HASH,
    AuditFields,
    compute_event_hash,
    verify_chain,
)


def make_fields(action: str = "test.action", event_id: str | None = None) -> AuditFields:
    return AuditFields(
        event_id=UUID(event_id or "0d9f0f6e-5f7a-4d8a-8b1c-8c1f5f2f0a11"),
        occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        actor_type="SERVICE",
        actor_id="audit-core",
        principal_name=None,
        service_name="audit-core",
        plane="OBSERVABILITY",
        action=action,
        resource_type="audit_event",
        resource_id="test",
        decision="INFO",
        reason="test",
        severity="INFO",
        request_id=None,
        correlation_id=None,
        trace_id=None,
        idempotency_key=None,
        data={"status": "ok"},
    )


def row_from_fields(seq: int, fields: AuditFields, prev_hash: str, event_hash: str) -> dict:
    return {
        "event_seq": seq,
        "prev_hash": prev_hash,
        "event_hash": event_hash,
        "event_id": fields.event_id,
        "occurred_at": fields.occurred_at,
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
    }


def test_hash_is_stable() -> None:
    fields = make_fields()

    h1 = compute_event_hash(fields, GENESIS_HASH)
    h2 = compute_event_hash(fields, GENESIS_HASH)

    assert h1 == h2
    assert len(h1) == 64


def test_hash_changes_with_prev_hash() -> None:
    fields = make_fields()

    h1 = compute_event_hash(fields, GENESIS_HASH)
    h2 = compute_event_hash(fields, "f" * 64)

    assert h1 != h2


def test_verify_chain_passes_for_valid_chain() -> None:
    prev = GENESIS_HASH
    rows = []

    for i in range(3):
        fields = make_fields(action=f"test.action.{i}")
        event_hash = compute_event_hash(fields, prev)
        rows.append(row_from_fields(i + 1, fields, prev, event_hash))
        prev = event_hash

    report = verify_chain(rows, GENESIS_HASH)

    assert report["ok"] is True
    assert report["events_checked"] == 3
    assert report["violations"] == []


def test_verify_chain_detects_tampering() -> None:
    prev = GENESIS_HASH
    rows = []

    for i in range(2):
        fields = make_fields(action=f"test.action.{i}")
        event_hash = compute_event_hash(fields, prev)
        rows.append(row_from_fields(i + 1, fields, prev, event_hash))
        prev = event_hash

    rows[1]["reason"] = "tampered"

    report = verify_chain(rows, GENESIS_HASH)

    assert report["ok"] is False
    assert any(v["type"] == "EVENT_HASH_MISMATCH" for v in report["violations"])