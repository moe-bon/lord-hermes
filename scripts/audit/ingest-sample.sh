#!/usr/bin/env bash
set -euo pipefail

HEADER_ARGS=()

if [[ -n "${APEX_AUDIT_INGEST_SHARED_SECRET:-}" ]]; then
  HEADER_ARGS=(-H "X-Audit-Ingest-Key: ${APEX_AUDIT_INGEST_SHARED_SECRET}")
fi

curl -sf -X POST http://localhost:8087/v1/audit/events \
  -H 'Content-Type: application/json' \
  "${HEADER_ARGS[@]}" \
  -d '{
    "actor_type": "SYSTEM",
    "service_name": "bootstrap",
    "plane": "CONTROL",
    "action": "audit.sample.created",
    "resource_type": "audit_system",
    "resource_id": "local",
    "decision": "INFO",
    "reason": "sample audit event",
    "severity": "INFO",
    "data": {
      "status": "ok"
    }
  }'