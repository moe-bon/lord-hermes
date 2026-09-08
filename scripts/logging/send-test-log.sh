#!/usr/bin/env bash
set -euo pipefail

curl -sf -X POST http://localhost:8088/v1/logs \
  -H 'Content-Type: application/json' \
  -d '{
    "logs": [
      {
        "level": "INFO",
        "service": "bootstrap",
        "service_version": "0.14.0",
        "environment": "local",
        "plane": "CONTROL",
        "event": "logging.test",
        "message": "structured logging test event",
        "data": {
          "status": "ok",
          "api_key": "this-must-be-redacted"
        }
      }
    ]
  }'