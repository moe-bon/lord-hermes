#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$ROOT/python/apexquant-migrations"

uv sync --all-extras

uv run apexquant-migrate verify \
  --engine postgres \
  --root "$ROOT/migrations/postgres" \
  --database-url "${APEX_POSTGRES_URL:?APEX_POSTGRES_URL must be set}"