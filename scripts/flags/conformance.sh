#!/usr/bin/env bash
# Cross-language conformance gate: identical fixture + identical verdicts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "=== Verifying determinism fixture is byte-identical across languages ==="
# The Rust crate include_str!s the fixture; a compile-time assert verifies the
# constants. We additionally hash the fixture so CI can pin it.
sha256sum "$ROOT/data/feature_flags/determinism.yaml"

echo "=== Rust evaluator conformance ==="
cargo test -p apex-flag-engine --test conformance

echo "=== Python evaluator conformance ==="
cd "$ROOT/python/apexquant-flags"
uv sync --all-extras
uv run pytest ../../tests/conformance/test_flag_conformance.py -q

echo "=== Randomized 10k verdict diff (Rust vs Python) ==="
uv run python "$ROOT/scripts/flags/randomized_diff.py"