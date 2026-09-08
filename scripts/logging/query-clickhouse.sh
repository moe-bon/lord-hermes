#!/usr/bin/env bash
set -euo pipefail

curl -sf 'http://localhost:8123/?database=logging' \
  --data-binary 'SELECT ts, level, service, event, message FROM structured_logs ORDER BY ts DESC LIMIT 20 FORMAT PrettyCompact'