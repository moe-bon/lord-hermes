#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FILE="${1:?usage: validate-service-manifest.sh <path-to-manifest>}"

cd "$ROOT/python/apexquant-config-validation"

uv sync --all-extras

uv run apexquant-config validate \
  --schema service_manifest/v1 \
  --file "$ROOT/$FILE"