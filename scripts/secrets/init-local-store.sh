#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$ROOT/python/apexquant-secrets"

uv sync --all-extras

uv run apexquant-secrets init-store \
    --store-path "$ROOT/infra/security/secrets/local.apexsecrets" \
    --audit-path "$ROOT/infra/security/audit/secrets-audit.jsonl" \
    --subject-service bootstrap \
    --subject-plane CONTROL