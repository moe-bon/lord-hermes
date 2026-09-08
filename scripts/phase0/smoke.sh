#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "ApexQuant Ultra Phase 0 Smoke Test"
echo "=================================="

FAIL=0

check_http() {
  local name="$1"
  local url="$2"
  echo "Checking HTTP: $name ($url)"
  if curl -sf --max-time 5 "$url" >/dev/null; then
    echo "  ✅ OK: $name"
  else
    echo "  ❌ FAIL: $name"
    FAIL=1
  fi
}

check_container_exec() {
  local service="$1"
  local cmd="$2"
  echo "Checking Exec: $service"
  local container_id
  container_id="$(./scripts/phase0/compose.sh ps -q "$service" || true)"
  if [[ -z "$container_id" ]]; then
    echo "  ❌ FAIL: $service is not running"
    FAIL=1
    return
  fi
  if docker exec "$container_id" sh -c "$cmd" >/dev/null 2>&1; then
    echo "  ✅ OK: $service"
  else
    echo "  ❌ FAIL: $service"
    FAIL=1
  fi
}

echo ""
echo "Infrastructure checks"
echo "---------------------"
check_container_exec "postgres" "pg_isready -U apex -d apexquant"
check_container_exec "redis" "redis-cli ping"
check_http "clickhouse" "http://localhost:8123/ping"
check_http "minio" "http://localhost:9000/minio/health/live"
check_container_exec "redpanda" "rpk cluster health"

echo ""
echo "HTTP Microservice checks"
echo "----------------------"
check_http "service-framework-core" "http://localhost:8080/healthz"
check_http "database-infrastructure-core" "http://localhost:8081/healthz"
check_http "api-gateway" "http://localhost:8085/healthz"
check_http "auth-core" "http://localhost:8086/healthz"
check_http "logging-core" "http://localhost:8088/healthz"
check_http "feature-flags-core" "http://localhost:8091/healthz"
check_http "config-validation-core" "http://localhost:8092/healthz"
check_http "backup-recovery-core" "http://localhost:8093/healthz"
check_http "disaster-recovery-core" "http://localhost:8094/healthz"

echo ""
if [[ "$FAIL" -ne 0 ]]; then
  echo "❌ Smoke test failed."
  exit 1
fi

echo "🎉 SMOKE TEST PASSED! Phase 0 is fully operational."
