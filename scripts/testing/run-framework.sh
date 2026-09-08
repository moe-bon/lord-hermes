#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$ROOT/python/apexquant-testing"

uv sync --all-extras

uv run apexquant-test-runner run \
  --root "$ROOT" \
  --package "$ROOT/python/apexquant-testing" \
  --output-dir "$ROOT/test-results" \
  --environment "${APEX_ENVIRONMENT:-local}" \
  --trigger script