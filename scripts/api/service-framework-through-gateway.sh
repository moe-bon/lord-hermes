#!/usr/bin/env bash
set -euo pipefail

curl -sf http://localhost:8085/api/service-framework-core/v1/services | jq .