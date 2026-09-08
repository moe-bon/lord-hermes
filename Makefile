# ApexQuant Ultra — Build & CI/CD Makefile
# Feature 0.18: CI/CD Pipeline

SHELL := /bin/bash
.DEFAULT_GOAL := help

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────
REGISTRY ?= ghcr.io
IMAGE_PREFIX ?= apexquant
VERSION ?= $(shell cat VERSION 2>/dev/null || echo "0.0.0-dev")
GIT_SHA ?= $(shell git rev-parse --short HEAD)
GIT_BRANCH ?= $(shell git rev-parse --abbrev-ref HEAD)
ENVIRONMENT ?= local

SERVICES := \
	service-framework-core \
	api-gateway \
	auth-core \
	audit-core \
	logging-core \
	tracing-core \
	event-bus-verifier

PYTHON_PACKAGES := $(wildcard python/*)

# ─────────────────────────────────────────────────────────────
# Help
# ─────────────────────────────────────────────────────────────
.PHONY: help
help: ## Show this help message
	@echo "ApexQuant Ultra — CI/CD Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

# ─────────────────────────────────────────────────────────────
# Development
# ─────────────────────────────────────────────────────────────
.PHONY: install
install: ## Install all dependencies
	@echo "Installing Python dependencies..."
	@for pkg in $(PYTHON_PACKAGES); do \
		if [ -f "$$pkg/pyproject.toml" ]; then \
			echo "  Installing $$pkg"; \
			cd $$pkg && uv sync --all-extras && cd ..; \
		fi; \
	done
	@echo "Installing Rust dependencies..."
	cargo fetch

.PHONY: format
format: ## Format all code
	@echo "Formatting Python..."
	@for pkg in $(PYTHON_PACKAGES); do \
		if [ -f "$$pkg/pyproject.toml" ]; then \
			cd $$pkg && uv run ruff format . && cd ..; \
		fi; \
	done
	@echo "Formatting Rust..."
	cargo fmt --all

.PHONY: lint
lint: ## Lint all code
	@echo "Linting Python..."
	@for pkg in $(PYTHON_PACKAGES); do \
		if [ -f "$$pkg/pyproject.toml" ]; then \
			cd $$pkg && uv run ruff check . && cd ..; \
		fi; \
	done
	@echo "Linting Rust..."
	cargo clippy --all-targets --all-features -- -D warnings

.PHONY: typecheck
typecheck: ## Type check all code
	@echo "Type checking Python..."
	@for pkg in $(PYTHON_PACKAGES); do \
		if [ -f "$$pkg/pyproject.toml" ]; then \
			cd $$pkg && uv run mypy . && cd ..; \
		fi; \
	done

# ─────────────────────────────────────────────────────────────
# Testing
# ─────────────────────────────────────────────────────────────
.PHONY: test
test: test-python test-rust ## Run all tests

.PHONY: test-python
test-python: ## Run Python tests
	@echo "Running Python tests..."
	@for pkg in $(PYTHON_PACKAGES); do \
		if [ -f "$$pkg/pyproject.toml" ] && [ -d "$$pkg/tests" ]; then \
			echo "  Testing $$pkg"; \
			cd $$pkg && uv run pytest --tb=short -q && cd ..; \
		fi; \
	done

.PHONY: test-rust
test-rust: ## Run Rust tests
	@echo "Running Rust tests..."
	cargo test --workspace

.PHONY: test-integration
test-integration: ## Run integration tests
	@echo "Running integration tests..."
	cd tests/integration && uv run pytest --tb=short -q

# ─────────────────────────────────────────────────────────────
# Security
# ─────────────────────────────────────────────────────────────
.PHONY: security
security: security-python security-rust security-secrets ## Run all security scans

.PHONY: security-python
security-python: ## Audit Python dependencies
	@echo "Auditing Python dependencies..."
	@for pkg in $(PYTHON_PACKAGES); do \
		if [ -f "$$pkg/pyproject.toml" ]; then \
			echo "  Auditing $$pkg"; \
			cd $$pkg && uv run pip-audit --skip-editable || true && cd ..; \
		fi; \
	done

.PHONY: security-rust
security-rust: ## Audit Rust dependencies
	@echo "Auditing Rust dependencies..."
	cargo audit

.PHONY: security-secrets
security-secrets: ## Scan for secrets
	@echo "Scanning for secrets..."
	@command -v gitleaks >/dev/null 2>&1 && gitleaks detect --no-banner || echo "gitleaks not installed, skipping"

# ─────────────────────────────────────────────────────────────
# Container Operations
# ─────────────────────────────────────────────────────────────
.PHONY: build
build: ## Build all container images
	@echo "Building container images..."
	@for svc in $(SERVICES); do \
		echo "  Building $$svc"; \
		docker build \
			-f infra/docker/dockerfiles/Dockerfile.$$svc \
			-t $(REGISTRY)/$(IMAGE_PREFIX)/$$svc:$(VERSION)-$(GIT_SHA) \
			. || exit 1; \
	done

.PHONY: build-%
build-%: ## Build a specific container image
	docker build \
		-f infra/docker/dockerfiles/Dockerfile.$* \
		-t $(REGISTRY)/$(IMAGE_PREFIX)/$*:$(VERSION)-$(GIT_SHA) \
		.

.PHONY: push
push: ## Push all container images
	@echo "Pushing container images..."
	@for svc in $(SERVICES); do \
		echo "  Pushing $$svc"; \
		docker push $(REGISTRY)/$(IMAGE_PREFIX)/$$svc:$(VERSION)-$(GIT_SHA) || exit 1; \
	done

.PHONY: scan
scan: ## Scan all container images
	@echo "Scanning container images..."
	@for svc in $(SERVICES); do \
		echo "  Scanning $$svc"; \
		trivy image --severity CRITICAL,HIGH \
			$(REGISTRY)/$(IMAGE_PREFIX)/$$svc:$(VERSION)-$(GIT_SHA) || exit 1; \
	done

.PHONY: sbom
sbom: ## Generate SBOM for all images
	@echo "Generating SBOMs..."
	@for svc in $(SERVICES); do \
		echo "  Generating SBOM for $$svc"; \
		syft $(REGISTRY)/$(IMAGE_PREFIX)/$$svc:$(VERSION)-$(GIT_SHA) \
			-o spdx-json=sbom-$$svc.spdx.json; \
	done

.PHONY: sign
sign: ## Sign all container images
	@echo "Signing container images..."
	@for svc in $(SERVICES); do \
		echo "  Signing $$svc"; \
		cosign sign --yes $(REGISTRY)/$(IMAGE_PREFIX)/$$svc:$(VERSION)-$(GIT_SHA); \
	done

# ─────────────────────────────────────────────────────────────
# Deployment
# ─────────────────────────────────────────────────────────────
.PHONY: deploy-sandbox
deploy-sandbox: ## Deploy to sandbox environment
	@echo "Deploying to sandbox..."
	ENVIRONMENT=sandbox ./scripts/deploy/deploy.sh

.PHONY: deploy-paper
deploy-paper: ## Deploy to paper environment
	@echo "Deploying to paper..."
	ENVIRONMENT=paper ./scripts/deploy/deploy.sh

.PHONY: deploy-production
deploy-production: ## Deploy to production (requires confirmation)
	@echo "⚠️  DEPLOYING TO PRODUCTION"
	@read -p "Are you sure? (yes/no): " confirm; \
	if [ "$$confirm" != "yes" ]; then echo "Deployment cancelled"; exit 1; fi
	ENVIRONMENT=production ./scripts/deploy/deploy.sh

.PHONY: rollback
rollback: ## Rollback to previous version
	@echo "Rolling back deployment..."
	./scripts/deploy/rollback.sh $(ENVIRONMENT)

# ─────────────────────────────────────────────────────────────
# Local Development
# ─────────────────────────────────────────────────────────────
.PHONY: up
up: ## Start local development environment
	docker compose \
		-f infra/docker/compose/local/docker-compose.yaml \
		-f infra/docker/compose/local/docker-compose.override.yaml \
		up -d --build

.PHONY: down
down: ## Stop local development environment
	docker compose \
		-f infra/docker/compose/local/docker-compose.yaml \
		-f infra/docker/compose/local/docker-compose.override.yaml \
		down

.PHONY: logs
logs: ## View local environment logs
	docker compose \
		-f infra/docker/compose/local/docker-compose.yaml \
		-f infra/docker/compose/local/docker-compose.override.yaml \
		logs -f

.PHONY: clean
clean: ## Clean build artifacts
	cargo clean
	rm -rf test-results/ sbom-*.spdx.json trivy-*.sarif
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true