#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$ROOT"

for package_dir in python/*/; do
  if [ -f "$package_dir/pyproject.toml" ] && [ -d "$package_dir/tests" ]; then
    echo "Testing $package_dir"

    pushd "$package_dir" > /dev/null

    uv sync --all-extras
    uv run pytest --tb=short -q

    popd > /dev/null
  fi
done