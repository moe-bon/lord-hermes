#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$ROOT/python/apexquant-secrets"

uv sync --all-extras

uv run apexquant-secrets scan-env \
    --path "$ROOT/.env.example" \
    --allow-examples