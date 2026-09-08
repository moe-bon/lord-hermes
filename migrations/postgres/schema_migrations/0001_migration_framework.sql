-- ApexQuant Ultra
-- Feature 0.20: Database Migration Framework
-- PostgreSQL migration registry and run audit.

BEGIN;

CREATE SCHEMA IF NOT EXISTS schema_migrations;

CREATE TABLE IF NOT EXISTS schema_migrations.applied_migrations (
    migration_id      TEXT PRIMARY KEY,
    engine            TEXT NOT NULL,
    domain            TEXT NOT NULL,
    version           TEXT NOT NULL,
    filename          TEXT NOT NULL,
    checksum_sha256   CHAR(64) NOT NULL,
    applied_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_by        TEXT NOT NULL DEFAULT 'unknown',
    execution_time_ms INTEGER,

    CONSTRAINT applied_migrations_engine_valid
        CHECK (engine IN ('postgres', 'clickhouse')),

    CONSTRAINT applied_migrations_domain_not_empty
        CHECK (length(trim(domain)) > 0),

    CONSTRAINT applied_migrations_version_not_empty
        CHECK (length(trim(version)) > 0),

    CONSTRAINT applied_migrations_filename_not_empty
        CHECK (length(trim(filename)) > 0),

    CONSTRAINT applied_migrations_checksum_format
        CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS schema_migrations_applied_engine_idx
    ON schema_migrations.applied_migrations (engine);

CREATE INDEX IF NOT EXISTS schema_migrations_applied_domain_idx
    ON schema_migrations.applied_migrations (domain);

CREATE INDEX IF NOT EXISTS schema_migrations_applied_applied_at_idx
    ON schema_migrations.applied_migrations (applied_at DESC);

CREATE TABLE IF NOT EXISTS schema_migrations.migration_runs (
    run_id         UUID PRIMARY KEY,
    engine         TEXT NOT NULL,
    mode           TEXT NOT NULL,
    status         TEXT NOT NULL,
    planned_count  INTEGER NOT NULL DEFAULT 0,
    applied_count  INTEGER NOT NULL DEFAULT 0,
    skipped_count  INTEGER NOT NULL DEFAULT 0,
    failed_count   INTEGER NOT NULL DEFAULT 0,
    error          TEXT,
    started_at     TIMESTAMPTZ NOT NULL,
    completed_at   TIMESTAMPTZ,
    metadata       JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT migration_runs_engine_valid
        CHECK (engine IN ('postgres', 'clickhouse')),

    CONSTRAINT migration_runs_status_valid
        CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),

    CONSTRAINT migration_runs_mode_valid
        CHECK (mode IN ('apply', 'baseline', 'verify', 'dry-run'))
);

CREATE INDEX IF NOT EXISTS schema_migrations_runs_started_at_idx
    ON schema_migrations.migration_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS schema_migrations_runs_status_idx
    ON schema_migrations.migration_runs (status);

CREATE TABLE IF NOT EXISTS schema_migrations.migration_locks (
    lock_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engine       TEXT NOT NULL,
    acquired_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    acquired_by  TEXT NOT NULL,
    expires_at   TIMESTAMPTZ,
    released_at  TIMESTAMPTZ,

    CONSTRAINT migration_locks_engine_valid
        CHECK (engine IN ('postgres', 'clickhouse')),

    CONSTRAINT migration_locks_acquired_by_not_empty
        CHECK (length(trim(acquired_by)) > 0)
);

CREATE INDEX IF NOT EXISTS schema_migrations_locks_engine_idx
    ON schema_migrations.migration_locks (engine, acquired_at DESC);

COMMIT;

