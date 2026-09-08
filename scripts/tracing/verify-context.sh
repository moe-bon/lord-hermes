#!/usr/bin/env bash
set -euo pipefail

TRACEPARENT="${1:-00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01}"

curl -sf -X POST http://localhost:8089/v1/tracing/context/verify \
  -H 'Content-Type: application/json' \
  -d "{\"traceparent\":\"${TRACEPARENT}\"}"