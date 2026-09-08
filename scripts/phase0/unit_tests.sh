#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "ApexQuant Ultra Phase 0 Unit Tests"
echo "=================================="

echo ""
echo "Running Rust tests inside Docker..."
echo "This may take a long time on first run because Rust dependencies compile."

docker run --rm \
  -v "$ROOT":/workspace \
  -w /workspace \
  rust:1.81-bookworm \
  bash -lc "apt-get update && apt-get install -y --no-install-recommends protobuf-compiler && cargo test --workspace"

echo ""
echo "Running Python package tests inside Docker..."

for package_dir in "$ROOT"/python/*/; do
  if [[ -f "$package_dir/pyproject.toml" ]]; then
    package_name="$(basename "$package_dir")"

    echo ""
    echo "Testing Python package: $package_name"

    if [[ -d "$package_dir/tests" ]]; then
      docker run --rm \
        -v "$ROOT":/workspace \
        -w "/workspace/python/$package_name" \
        python:3.13-slim \
        bash -lc "pip install --no-cache-dir .[dev] && pytest -q"
    else
      echo "No tests directory found for $package_name; skipping tests."
    fi
  fi
done

echo ""
echo "Unit test pass completed."