#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "ApexQuant Ultra Repository Check"
echo "================================"

MISSING=0

check_dir() {
  local dir="$1"

  if [[ -d "$dir" ]]; then
    echo "OK dir: $dir"
  else
    echo "MISSING dir: $dir"
    MISSING=1
  fi
}

check_file() {
  local file="$1"

  if [[ -f "$file" ]]; then
    echo "OK file: $file"
  else
    echo "MISSING file: $file"
    MISSING=1
  fi
}

check_dir "proto"
check_dir "crates"
check_dir "python"
check_dir "migrations/postgres"
check_dir "infra/docker/compose/local"
check_dir "infra/docker/dockerfiles"
check_dir "scripts"

check_file "Cargo.toml"
check_file "rust-toolchain.toml"
check_file "Makefile"

# Phase 0 migration domains
check_dir "migrations/postgres/service_framework"
check_dir "migrations/postgres/config_management"
check_dir "migrations/postgres/secrets_management"
check_dir "migrations/postgres/database_infrastructure"
check_dir "migrations/postgres/event_bus"
check_dir "migrations/postgres/object_storage"
check_dir "migrations/postgres/api_gateway"
check_dir "migrations/postgres/auth"
check_dir "migrations/postgres/rbac"
check_dir "migrations/postgres/audit"
check_dir "migrations/postgres/logging"
check_dir "migrations/postgres/metrics"
check_dir "migrations/postgres/tracing"
check_dir "migrations/postgres/health"
check_dir "migrations/postgres/cicd"
check_dir "migrations/postgres/testing"
check_dir "migrations/postgres/schema_migrations"
check_dir "migrations/postgres/service_versioning"
check_dir "migrations/postgres/feature_flags"
check_dir "migrations/postgres/config_validation"
check_dir "migrations/postgres/backup_recovery"
check_dir "migrations/postgres/disaster_recovery"

# Critical compose files
check_file "infra/docker/compose/local/docker-compose.yaml"
check_file "infra/docker/compose/local/docker-compose.override.yaml"

echo ""
if [[ "$MISSING" -ne 0 ]]; then
  echo "Repository check failed."
  echo "Copy the missing files from the corresponding feature responses."
  exit 1
fi

echo "Repository check passed."