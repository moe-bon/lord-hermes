#!/usr/bin/env bash
set -euo pipefail

TOKEN="${1:?usage: ./scripts/auth/verify-token.sh <token>}"

curl -sf http://localhost:8086/v1/auth/verify \
  -H "Authorization: Bearer ${TOKEN}"