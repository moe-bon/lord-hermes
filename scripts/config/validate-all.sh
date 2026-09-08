#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$ROOT/python/apexquant-config-validation"

uv sync --all-extras

uv run apexquant-config validate-all --root "$ROOT/config"