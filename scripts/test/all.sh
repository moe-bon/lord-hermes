#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$ROOT"

cargo test --workspace

cd "$ROOT/python/apexquant-service-framework"
uv sync --all-extras
uv run pytest

cd "$ROOT/python/apexquant-repo-architecture"
uv sync --all-extras
uv run pytest