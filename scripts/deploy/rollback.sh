#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ENVIRONMENT="${1:-sandbox}"

echo "============================================"
echo "  ApexQuant Ultra Rollback"
echo "  Environment: ${ENVIRONMENT}"
echo "============================================"

# Find the previous deployment
PREVIOUS_DEPLOYMENT="deployments/${ENVIRONMENT}-previous.json"
CURRENT_DEPLOYMENT="deployments/${ENVIRONMENT}-latest.json"

if [ ! -f "${CURRENT_DEPLOYMENT}" ]; then
    echo "✗ No current deployment found for ${ENVIRONMENT}"
    exit 1
fi

if [ ! -f "${PREVIOUS_DEPLOYMENT}" ]; then
    echo "✗ No previous deployment found for rollback"
    exit 1
fi

PREVIOUS_VERSION=$(jq -r '.version' "${PREVIOUS_DEPLOYMENT}")
CURRENT_VERSION=$(jq -r '.version' "${CURRENT_DEPLOYMENT}")

echo ""
echo "  Rolling back: ${CURRENT_VERSION} → ${PREVIOUS_VERSION}"
echo ""

# Archive current deployment
mv "${CURRENT_DEPLOYMENT}" "deployments/${ENVIRONMENT}-rolled-back-$(date +%s).json"

# Restore previous deployment
cp "${PREVIOUS_DEPLOYMENT}" "${CURRENT_DEPLOYMENT}"

echo "✓ Rollback complete"
echo "  Environment ${ENVIRONMENT} is now at version ${PREVIOUS_VERSION}"