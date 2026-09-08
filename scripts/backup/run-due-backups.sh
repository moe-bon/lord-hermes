#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$ROOT/python/apexquant-backup-recovery"

uv sync --all-extras

uv run apexquant-backup-recovery run-due