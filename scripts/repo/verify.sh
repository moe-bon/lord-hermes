#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$ROOT/python/apexquant-repo-architecture"

uv sync --all-extras

uv run apexquant-repo-verify \
    --repo-root "$ROOT" \
    --strict-warnings \
    --json