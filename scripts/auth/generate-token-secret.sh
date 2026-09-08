#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
import base64
import secrets

print(base64.b64encode(secrets.token_bytes(32)).decode())
PY