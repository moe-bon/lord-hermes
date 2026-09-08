#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$ROOT"

docker compose \
  -f infra/docker/compose/local/docker-compose.yaml \
  -f infra/docker/compose/local/docker-compose.override.yaml \
  -f infra/docker/compose/local/docker-compose.event-bus.yaml \
  --profile tools \
  run --rm event-bus-verifier \
  bootstrap \
  --bootstrap-servers "${APEX_KAFKA_BOOTSTRAP_SERVERS:-redpanda:9092}" \
  --environment "${APEX_ENVIRONMENT:-local}"