#!/usr/bin/env bash
set -euo pipefail

HEADER_ARGS=()

if [[ -n "${APEX_AUDIT_INGEST_SHARED_SECRET:-}" ]]; then
  HEADER_ARGS=(-H "X-Audit-Ingest-Key: ${APEX_AUDIT_INGEST_SHARED_SECRET}")
fi

curl -sf "http://localhost:8087/v1/audit/verify?limit=1000" \
  "${HEADER_ARGS[@]}"