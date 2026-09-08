#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
ENV_FILE="$ROOT/.env"

FILES=( "infra/docker/compose/local/docker-compose.yaml" )
for f in infra/docker/compose/local/docker-compose.*.yaml; do
  [[ -f "$f" ]] && FILES+=("$f")
done

ARGS=()
for file in "${FILES[@]}"; do
  ARGS+=("-f" "$file")
done

exec docker compose --env-file "$ENV_FILE" "${ARGS[@]}" "$@"
