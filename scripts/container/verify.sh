#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$ROOT/python/apexquant-container-policy"

uv sync --all-extras

uv run apexquant-container-policy \
    --compose "$ROOT/infra/docker/compose/local/docker-compose.yaml" \
    --json