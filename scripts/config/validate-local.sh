#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$ROOT/python/apexquant-env-config"

uv sync --all-extras

uv run apexquant-env-config \
    --environments-root "$ROOT/infra/environments" \
    --environment local \
    --json