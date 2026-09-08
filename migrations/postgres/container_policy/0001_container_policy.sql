-- ApexQuant Ultra
-- Feature 0.3: Docker Containerization & Service Isolation
-- PostgreSQL container policy verification audit.

BEGIN;

CREATE SCHEMA IF NOT EXISTS container_policy;

CREATE TABLE IF NOT EXISTS container_policy.verification_runs (
    run_id UUID PRIMARY KEY,
    compose_path TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    ok BOOLEAN NOT NULL,
    errors_count INTEGER NOT NULL,
    warnings_count INTEGER NOT NULL,
    services_checked JSONB NOT NULL,
    violations JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT verification_runs_errors_count_nonnegative
        CHECK (errors_count >= 0),

    CONSTRAINT verification_runs_warnings_count_nonnegative
        CHECK (warnings_count >= 0),

    CONSTRAINT verification_runs_started_before_completed
        CHECK (started_at <= completed_at)
);

CREATE INDEX IF NOT EXISTS container_policy_verification_runs_started_at_idx
    ON container_policy.verification_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS container_policy_verification_runs_ok_idx
    ON container_policy.verification_runs (ok);

CREATE INDEX IF NOT EXISTS container_policy_verification_runs_created_at_idx
    ON container_policy.verification_runs (created_at DESC);

CREATE TABLE IF NOT EXISTS container_policy.verification_violations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id UUID NOT NULL
        REFERENCES container_policy.verification_runs(run_id)
        ON DELETE CASCADE,
    service_name TEXT NOT NULL,
    code TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,

    CONSTRAINT verification_violations_severity_valid
        CHECK (severity IN ('ERROR', 'WARNING')),

    CONSTRAINT verification_violations_service_name_not_empty
        CHECK (length(trim(service_name)) > 0),

    CONSTRAINT verification_violations_code_not_empty
        CHECK (length(trim(code)) > 0),

    CONSTRAINT verification_violations_message_not_empty
        CHECK (length(trim(message)) > 0)
);

CREATE INDEX IF NOT EXISTS container_policy_verification_violations_run_id_idx
    ON container_policy.verification_violations (run_id);

CREATE INDEX IF NOT EXISTS container_policy_verification_violations_service_name_idx
    ON container_policy.verification_violations (service_name);

CREATE INDEX IF NOT EXISTS container_policy_verification_violations_code_idx
    ON container_policy.verification_violations (code);

CREATE INDEX IF NOT EXISTS container_policy_verification_violations_severity_idx
    ON container_policy.verification_violations (severity);

COMMIT;