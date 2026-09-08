# ApexQuant Ultra

ApexQuant Ultra is an institutional-grade, AI-assisted trading platform built around a deterministic safety boundary.

## Core Rule

AI proposes.

Risk authorizes.

Execution executes.

Reconciliation verifies.

## Repository Planes

- `crates/` — Rust crates for deterministic and performance-critical services.
- `python/` — Python packages for intelligence, orchestration, research, and tooling.
- `services/` — deployable service definitions grouped by system plane.
- `proto/` — versioned Protobuf contracts.
- `migrations/` — PostgreSQL, ClickHouse, Qdrant, and Kafka schema changes.
- `infra/` — Docker, Kubernetes, monitoring, security, and environment definitions.
- `docs/` — architecture, runbooks, ADRs, and feature documentation.
- `scripts/` — repository automation.
- `tests/` — cross-service test suites.

## Base Commands

```bash
make format
make lint
make test
make repo-verify
make compose-up