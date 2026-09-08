#!/usr/bin/env bash
set -euo pipefail

curl -sf -X POST http://localhost:8089/v1/tracing/test-span \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "apex.tracing.manual-test"
  }'