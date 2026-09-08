-- ApexQuant Ultra
-- Feature 0.15: Metrics Infrastructure
-- PostgreSQL metric metadata, SLO, and alert rule registry.

BEGIN;

CREATE SCHEMA IF NOT EXISTS metrics;

DO $$
BEGIN
    CREATE TYPE metrics.metric_type AS ENUM (
        'COUNTER',
        'GAUGE',
        'HISTOGRAM',
        'SUMMARY'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE TABLE IF NOT EXISTS metrics.metric_definitions (
    metric_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name           TEXT NOT NULL UNIQUE,
    metric_type    metrics.metric_type NOT NULL,
    subsystem      TEXT NOT NULL,
    unit           TEXT NOT NULL DEFAULT '',
    description    TEXT NOT NULL DEFAULT '',
    allowed_labels TEXT[] NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT metric_definitions_name_format
        CHECK (name ~ '^apexquant_[a-z0-9_]+_[a-z0-9_]+(_[a-z]+)?$'),

    CONSTRAINT metric_definitions_subsystem_not_empty
        CHECK (length(trim(subsystem)) > 0)
);

CREATE INDEX IF NOT EXISTS metrics_definitions_subsystem_idx
    ON metrics.metric_definitions (subsystem);

CREATE TABLE IF NOT EXISTS metrics.service_level_objectives (
    slo_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name           TEXT NOT NULL UNIQUE,
    metric_name    TEXT NOT NULL REFERENCES metrics.metric_definitions(name) ON DELETE CASCADE,
    target         NUMERIC NOT NULL,
    window_seconds INTEGER NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT slo_target_valid CHECK (target > 0 AND target <= 100),
    CONSTRAINT slo_window_positive CHECK (window_seconds > 0)
);

CREATE TABLE IF NOT EXISTS metrics.alert_rules (
    alert_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name           TEXT NOT NULL UNIQUE,
    promql_expr    TEXT NOT NULL,
    severity       TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    runbook_url    TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT alert_rules_severity_valid
        CHECK (severity IN ('CRITICAL', 'WARNING', 'INFO'))
);

CREATE OR REPLACE FUNCTION metrics.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS metrics_definitions_updated_at ON metrics.metric_definitions;
CREATE TRIGGER metrics_definitions_updated_at
BEFORE UPDATE ON metrics.metric_definitions
FOR EACH ROW EXECUTE FUNCTION metrics.set_updated_at();

DROP TRIGGER IF EXISTS alert_rules_updated_at ON metrics.alert_rules;
CREATE TRIGGER alert_rules_updated_at
BEFORE UPDATE ON metrics.alert_rules
FOR EACH ROW EXECUTE FUNCTION metrics.set_updated_at();

COMMIT;