-- ApexQuant Ultra
-- Feature 0.14: Structured Logging Infrastructure
-- PostgreSQL logging configuration metadata.

BEGIN;

CREATE SCHEMA IF NOT EXISTS logging;

DO $$
BEGIN
    CREATE TYPE logging.sink_type AS ENUM (
        'STDOUT',
        'FILE',
        'LOKI',
        'CLICKHOUSE'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE OR REPLACE FUNCTION logging.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS logging.service_log_configs (
    service_name       TEXT PRIMARY KEY,
    environment        TEXT NOT NULL,
    plane              TEXT NOT NULL,
    default_level      TEXT NOT NULL DEFAULT 'INFO',
    json_output        BOOLEAN NOT NULL DEFAULT TRUE,
    redaction_enabled  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT service_log_configs_service_name_not_empty
        CHECK (length(trim(service_name)) > 0),

    CONSTRAINT service_log_configs_environment_not_empty
        CHECK (length(trim(environment)) > 0),

    CONSTRAINT service_log_configs_plane_not_empty
        CHECK (length(trim(plane)) > 0),

    CONSTRAINT service_log_configs_default_level_valid
        CHECK (default_level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'))
);

DROP TRIGGER IF EXISTS logging_service_log_configs_updated_at_trigger
    ON logging.service_log_configs;

CREATE TRIGGER logging_service_log_configs_updated_at_trigger
BEFORE UPDATE ON logging.service_log_configs
FOR EACH ROW
EXECUTE FUNCTION logging.set_updated_at();

CREATE TABLE IF NOT EXISTS logging.level_overrides (
    override_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name   TEXT NOT NULL
        REFERENCES logging.service_log_configs(service_name)
        ON DELETE CASCADE,
    module_name    TEXT NOT NULL DEFAULT '*',
    level          TEXT NOT NULL,
    expires_at     TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT level_overrides_level_valid
        CHECK (level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),

    CONSTRAINT level_overrides_module_name_not_empty
        CHECK (length(trim(module_name)) > 0)
);

CREATE INDEX IF NOT EXISTS logging_level_overrides_service_idx
    ON logging.level_overrides (service_name);

CREATE INDEX IF NOT EXISTS logging_level_overrides_expires_idx
    ON logging.level_overrides (expires_at);

CREATE TABLE IF NOT EXISTS logging.sinks (
    sink_name   TEXT PRIMARY KEY,
    sink_type   logging.sink_type NOT NULL,
    endpoint    TEXT,
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT sinks_sink_name_not_empty
        CHECK (length(trim(sink_name)) > 0)
);

DROP TRIGGER IF EXISTS logging_sinks_updated_at_trigger
    ON logging.sinks;

CREATE TRIGGER logging_sinks_updated_at_trigger
BEFORE UPDATE ON logging.sinks
FOR EACH ROW
EXECUTE FUNCTION logging.set_updated_at();

INSERT INTO logging.sinks (sink_name, sink_type, endpoint, active)
VALUES
    ('stdout', 'STDOUT', NULL, TRUE),
    ('clickhouse', 'CLICKHOUSE', 'http://clickhouse:8123', TRUE),
    ('loki', 'LOKI', 'http://loki:3100', TRUE)
ON CONFLICT (sink_name) DO NOTHING;

COMMIT;