#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$ROOT"

cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings

buf lint

uv run ruff check python scripts tests
uv run mypy python/apexquant-service-framework/src
uv run mypy python/apexquant-repo-architecture/src