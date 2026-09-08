-- ApexQuant Ultra
-- PostgreSQL tracing configuration and verification metadata.

BEGIN;

CREATE SCHEMA IF NOT EXISTS tracing;

CREATE OR REPLACE FUNCTION tracing.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS tracing.service_tracing_configs (
    service_name       TEXT PRIMARY KEY,
    environment        TEXT NOT NULL,
    plane              TEXT NOT NULL,
    otlp_endpoint      TEXT,
    tempo_query_endpoint TEXT,
    sample_ratio       NUMERIC(5,4) NOT NULL DEFAULT 1.0,
    tracing_enabled    BOOLEAN NOT NULL DEFAULT TRUE,
    redaction_enabled  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT service_tracing_configs_service_name_not_empty
        CHECK (length(trim(service_name)) > 0),

    CONSTRAINT service_tracing_configs_environment_not_empty
        CHECK (length(trim(environment)) > 0),

    CONSTRAINT service_tracing_configs_plane_not_empty
        CHECK (length(trim(plane)) > 0),

    CONSTRAINT service_tracing_configs_sample_ratio_valid
        CHECK (sample_ratio >= 0 AND sample_ratio <= 1)
);

DROP TRIGGER IF EXISTS service_tracing_configs_updated_at_trigger
    ON tracing.service_tracing_configs;

CREATE TRIGGER service_tracing_configs_updated_at_trigger
BEFORE UPDATE ON tracing.service_tracing_configs
FOR EACH ROW
EXECUTE FUNCTION tracing.set_updated_at();

CREATE TABLE IF NOT EXISTS tracing.sampling_policies (
    policy_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name    TEXT NOT NULL
        REFERENCES tracing.service_tracing_configs(service_name)
        ON DELETE CASCADE,
    route_pattern   TEXT NOT NULL DEFAULT '*',
    sample_ratio    NUMERIC(5,4) NOT NULL,
    priority        INTEGER NOT NULL DEFAULT 100,
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT sampling_policies_route_pattern_not_empty
        CHECK (length(trim(route_pattern)) > 0),

    CONSTRAINT sampling_policies_sample_ratio_valid
        CHECK (sample_ratio >= 0 AND sample_ratio <= 1),

    CONSTRAINT sampling_policies_priority_positive
        CHECK (priority > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS sampling_policies_service_route_priority_uq
    ON tracing.sampling_policies (service_name, route_pattern, priority);

DROP TRIGGER IF EXISTS sampling_policies_updated_at_trigger
    ON tracing.sampling_policies;

CREATE TRIGGER sampling_policies_updated_at_trigger
BEFORE UPDATE ON tracing.sampling_policies
FOR EACH ROW
EXECUTE FUNCTION tracing.set_updated_at();

CREATE TABLE IF NOT EXISTS tracing.pipeline_verification_runs (
    run_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment        TEXT NOT NULL,
    tempo_query_endpoint TEXT,
    generated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    ok                 BOOLEAN NOT NULL,
    trace_id           TEXT,
    report             JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT pipeline_verification_runs_environment_not_empty
        CHECK (length(trim(environment)) > 0)
);

CREATE INDEX IF NOT EXISTS pipeline_verification_runs_generated_at_idx
    ON tracing.pipeline_verification_runs (generated_at DESC);

CREATE INDEX IF NOT EXISTS pipeline_verification_runs_ok_idx
    ON tracing.pipeline_verification_runs (ok);

COMMIT;