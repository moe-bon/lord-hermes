#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

EXPECTED_SHA="$(sha256sum data/rbac/forbidden_matrix.yaml | awk '{print $1}')"
echo "canonical matrix sha256: ${EXPECTED_SHA}"

# 1. Rust embedded matrix must equal the canonical file (drift check).
cargo test --package apex-rbac -- --nocapture

# 2. Python-loaded matrix must equal the canonical file.
PY_SHA="$(cd python/apexquant-auth && uv run python -c 'from apexquant_auth.rbac import matrix_sha256; print(matrix_sha256())')"
if [[ "${PY_SHA}" != "${EXPECTED_SHA}" ]]; then
  echo "DRIFT: python matrix sha256 ${PY_SHA} != canonical ${EXPECTED_SHA}" >&2
  exit 1
fi

# 3. Both evaluators already assert identical verdicts on the shared vectors
#    inside their respective test suites (cargo test + pytest).
cd python/apexquant-auth && uv run pytest -q

echo "RBAC cross-language conformance PASSED"