#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ENVIRONMENT="${ENVIRONMENT:-sandbox}"
VERSION="${VERSION:-$(cat VERSION 2>/dev/null || echo '0.0.0-dev')}"
GIT_SHA="${GIT_SHA:-$(git rev-parse --short HEAD)}"
REGISTRY="${REGISTRY:-ghcr.io}"
IMAGE_PREFIX="${IMAGE_PREFIX:-apexquant}"

echo "============================================"
echo "  ApexQuant Ultra Deployment"
echo "============================================"
echo "  Environment: ${ENVIRONMENT}"
echo "  Version:     ${VERSION}"
echo "  Git SHA:     ${GIT_SHA}"
echo "  Registry:    ${REGISTRY}"
echo "============================================"

# Validate environment
case "${ENVIRONMENT}" in
    sandbox|paper|shadow|production)
        echo "✓ Valid environment: ${ENVIRONMENT}"
        ;;
    *)
        echo "✗ Invalid environment: ${ENVIRONMENT}"
        exit 1
        ;;
esac

# Production requires additional verification
if [ "${ENVIRONMENT}" = "production" ]; then
    echo ""
    echo "⚠️  PRODUCTION DEPLOYMENT CHECKLIST:"
    echo "  - All CI gates passed"
    echo "  - Security scans clean"
    echo "  - Paper trading verified"
    echo "  - Rollback procedure documented"
    echo ""

    if [ -z "${DEPLOY_APPROVED:-}" ]; then
        echo "✗ Production deployment requires DEPLOY_APPROVED=true"
        exit 1
    fi
fi

# Record deployment
echo ""
echo "Recording deployment..."
echo "{
    \"service\": \"all\",
    \"environment\": \"${ENVIRONMENT}\",
    \"version\": \"${VERSION}\",
    \"git_sha\": \"${GIT_SHA}\",
    \"deployed_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
    \"deployed_by\": \"$(whoami)\"
}" > "deployments/${ENVIRONMENT}-latest.json"

mkdir -p deployments
echo "✓ Deployment recorded"

echo ""
echo "============================================"
echo "  Deployment to ${ENVIRONMENT} complete"
echo "============================================"