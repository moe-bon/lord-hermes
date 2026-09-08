#!/usr/bin/env bash
set -euo pipefail

echo "ApexQuant Ultra Phase 0 Preflight"
echo "================================="

MISSING=0

require() {
  local cmd="$1"

  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "MISSING: $cmd"
    MISSING=1
  else
    echo "OK: $cmd"
  fi
}

require git
require curl
require jq
require make
require openssl
require docker

echo ""
echo "Docker version:"
docker version --format '{{.Server.Version}}' || {
  echo "Docker daemon is not running or current user has no Docker access."
  exit 1
}

echo ""
echo "Docker Compose version:"
docker compose version

echo ""
echo "Disk usage:"
df -h .

echo ""
echo "Memory:"
free -h

if [[ "$MISSING" -ne 0 ]]; then
  echo ""
  echo "Preflight failed. Install missing tools first."
  exit 1
fi

echo ""
echo "Preflight passed."