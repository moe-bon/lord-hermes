#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$ROOT/python/apexquant-backup-recovery"

uv sync --all-extras

uv run apexquant-backup-recovery create-policy \
  --name local-postgres \
  --target-system POSTGRES \
  --target-name apexquant \
  --connection-ref env://APEX_BACKUP_POSTGRES_URL \
  --bucket apexquant-backups \
  --prefix backups/ \
  --interval-minutes 1440 \
  --retention-count 7 \
  --retention-days 30