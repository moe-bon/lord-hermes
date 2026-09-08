-- ApexQuant Ultra
-- Feature 0.7: Redis Infrastructure
-- PostgreSQL cache infrastructure verification audit.

BEGIN;

CREATE SCHEMA IF NOT EXISTS cache_infrastructure;

CREATE TABLE IF NOT EXISTS cache_infrastructure.verification_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment TEXT NOT NULL,
    instance_name TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    ok BOOLEAN NOT NULL,
    errors_count INTEGER NOT NULL,
    warnings_count INTEGER NOT NULL,
    report JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT cache_verification_environment_not_empty
        CHECK (length(trim(environment)) > 0),

    CONSTRAINT cache_verification_instance_name_not_empty
        CHECK (length(trim(instance_name)) > 0),

    CONSTRAINT cache_verification_errors_count_nonnegative
        CHECK (errors_count >= 0),

    CONSTRAINT cache_verification_warnings_count_nonnegative
        CHECK (warnings_count >= 0)
);

CREATE INDEX IF NOT EXISTS cache_infrastructure_verification_runs_started_at_idx
    ON cache_infrastructure.verification_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS cache_infrastructure_verification_runs_ok_idx
    ON cache_infrastructure.verification_runs (ok);

COMMIT;