#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://localhost:8090"

curl -sf -X POST "${BASE_URL}/v1/services" \
  -H 'Content-Type: application/json' \
  -d '{
    "service_name": "example-service",
    "plane": "CONTROL",
    "description": "Example service for versioning demo"
  }'

curl -sf -X POST "${BASE_URL}/v1/services/example-service/versions" \
  -H 'Content-Type: application/json' \
  -d '{
    "version": "1.0.0",
    "api_version": "v1",
    "metadata": {
      "team": "platform"
    }
  }'

curl -sf -X POST "${BASE_URL}/v1/services/example-service/versions/1.0.0/release" \
  -H 'Content-Type: application/json' \
  -d '{
    "git_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "image_tag": "apexquant/example-service:1.0.0",
    "checksum_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "actor": "release-manager",
    "reason": "example release"
  }'

curl -sf "${BASE_URL}/v1/services/example-service/versions/1.0.0/compatibility"