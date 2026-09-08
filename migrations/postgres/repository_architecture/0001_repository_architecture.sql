-- ApexQuant Ultra
-- Feature 0.2: Repository & Codebase Architecture
-- PostgreSQL repository architecture verification audit.

BEGIN;

CREATE SCHEMA IF NOT EXISTS repository_architecture;

CREATE TABLE IF NOT EXISTS repository_architecture.verification_runs (
    run_id UUID PRIMARY KEY,
    repo_root TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    ok BOOLEAN NOT NULL,
    errors_count INTEGER NOT NULL,
    warnings_count INTEGER NOT NULL,
    checked_paths JSONB NOT NULL,
    cargo_members JSONB NOT NULL,
    python_packages JSONB NOT NULL,
    violations JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT verification_runs_errors_count_nonnegative
        CHECK (errors_count >= 0),

    CONSTRAINT verification_runs_warnings_count_nonnegative
        CHECK (warnings_count >= 0),

    CONSTRAINT verification_runs_started_before_completed
        CHECK (started_at <= completed_at)
);

CREATE INDEX IF NOT EXISTS verification_runs_started_at_idx
    ON repository_architecture.verification_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS verification_runs_ok_idx
    ON repository_architecture.verification_runs (ok);

CREATE INDEX IF NOT EXISTS verification_runs_created_at_idx
    ON repository_architecture.verification_runs (created_at DESC);

CREATE TABLE IF NOT EXISTS repository_architecture.verification_violations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id UUID NOT NULL
        REFERENCES repository_architecture.verification_runs(run_id)
        ON DELETE CASCADE,
    code TEXT NOT NULL,
    severity TEXT NOT NULL,
    path TEXT NOT NULL,
    message TEXT NOT NULL,

    CONSTRAINT verification_violations_severity_valid
        CHECK (severity IN ('ERROR', 'WARNING')),

    CONSTRAINT verification_violations_code_not_empty
        CHECK (length(trim(code)) > 0),

    CONSTRAINT verification_violations_path_not_empty
        CHECK (length(trim(path)) > 0),

    CONSTRAINT verification_violations_message_not_empty
        CHECK (length(trim(message)) > 0)
);

CREATE INDEX IF NOT EXISTS verification_violations_run_id_idx
    ON repository_architecture.verification_violations (run_id);

CREATE INDEX IF NOT EXISTS verification_violations_code_idx
    ON repository_architecture.verification_violations (code);

CREATE INDEX IF NOT EXISTS verification_violations_severity_idx
    ON repository_architecture.verification_violations (severity);

COMMIT;