#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
import base64
import secrets

identifier = base64.urlsafe_b64encode(secrets.token_bytes(12)).rstrip(b"=").decode()
secret = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()

print(f"{identifier}.{secret}")
PY