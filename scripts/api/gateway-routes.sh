#!/usr/bin/env bash
set -euo pipefail

curl -sf http://localhost:8085/v1/gateway/routes | jq .