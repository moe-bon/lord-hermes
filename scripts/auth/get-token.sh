#!/usr/bin/env bash
set -euo pipefail

: "${APEX_AUTH_BOOTSTRAP_API_KEY:?APEX_AUTH_BOOTSTRAP_API_KEY must be set}"

curl -sf -X POST http://localhost:8086/v1/auth/tokens \
  -H 'Content-Type: application/json' \
  -d "{\"api_key\":\"${APEX_AUTH_BOOTSTRAP_API_KEY}\",\"ttl_seconds\":300}"