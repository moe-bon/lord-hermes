-- ApexQuant Ultra
-- Feature 0.23: Configuration Validation
-- PostgreSQL configuration registry, validation runs, and audit events.

BEGIN;

CREATE SCHEMA IF NOT EXISTS config_validation;

DO $$
BEGIN
    CREATE TYPE config_validation.config_document_status AS ENUM (
        'DRAFT',
        'ACTIVE',
        'RETIRED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE OR REPLACE FUNCTION config_validation.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION config_validation.prevent_event_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'configuration events are append-only';
END
$$;

CREATE TABLE IF NOT EXISTS config_validation.config_schemas (
    schema_key     TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    json_schema    JSONB NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (schema_key, schema_version),

    CONSTRAINT config_schemas_schema_key_not_empty
        CHECK (length(trim(schema_key)) > 0),

    CONSTRAINT config_schemas_schema_version_not_empty
        CHECK (length(trim(schema_version)) > 0)
);

DROP TRIGGER IF EXISTS config_schemas_updated_at_trigger
    ON config_validation.config_schemas;

CREATE TRIGGER config_schemas_updated_at_trigger
BEFORE UPDATE ON config_validation.config_schemas
FOR EACH ROW
EXECUTE FUNCTION config_validation.set_updated_at();

CREATE TABLE IF NOT EXISTS config_validation.config_documents (
    document_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    schema_key     TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    service_name   TEXT,
    environment    TEXT,
    config_hash    CHAR(64) NOT NULL,
    values         JSONB NOT NULL,
    status         config_validation.config_document_status NOT NULL DEFAULT 'DRAFT',
    created_by     TEXT NOT NULL DEFAULT 'system',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT config_documents_schema_key_not_empty
        CHECK (length(trim(schema_key)) > 0),

    CONSTRAINT config_documents_schema_version_not_empty
        CHECK (length(trim(schema_version)) > 0),

    CONSTRAINT config_documents_hash_format
        CHECK (config_hash ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS config_documents_service_idx
    ON config_validation.config_documents (service_name);

CREATE INDEX IF NOT EXISTS config_documents_environment_idx
    ON config_validation.config_documents (environment);

CREATE INDEX IF NOT EXISTS config_documents_schema_idx
    ON config_validation.config_documents (schema_key, schema_version);

CREATE INDEX IF NOT EXISTS config_documents_status_idx
    ON config_validation.config_documents (status);

DROP TRIGGER IF EXISTS config_documents_updated_at_trigger
    ON config_validation.config_documents;

CREATE TRIGGER config_documents_updated_at_trigger
BEFORE UPDATE ON config_validation.config_documents
FOR EACH ROW
EXECUTE FUNCTION config_validation.set_updated_at();

CREATE TABLE IF NOT EXISTS config_validation.config_validation_runs (
    run_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id  UUID REFERENCES config_validation.config_documents(document_id) ON DELETE SET NULL,
    schema_key   TEXT NOT NULL,
    environment  TEXT,
    trigger      TEXT NOT NULL DEFAULT 'manual',
    ok           BOOLEAN NOT NULL,
    errors       JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings     JSONB NOT NULL DEFAULT '[]'::jsonb,
    config_hash  CHAR(64),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT config_validation_runs_schema_key_not_empty
        CHECK (length(trim(schema_key)) > 0),

    CONSTRAINT config_validation_runs_trigger_not_empty
        CHECK (length(trim(trigger)) > 0)
);

CREATE INDEX IF NOT EXISTS config_validation_runs_created_at_idx
    ON config_validation.config_validation_runs (created_at DESC);

CREATE INDEX IF NOT EXISTS config_validation_runs_ok_idx
    ON config_validation.config_validation_runs (ok);

CREATE TABLE IF NOT EXISTS config_validation.config_events (
    event_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES config_validation.config_documents(document_id) ON DELETE CASCADE,
    event_type  TEXT NOT NULL,
    actor       TEXT NOT NULL,
    reason      TEXT NOT NULL DEFAULT '',
    before_hash CHAR(64),
    after_hash  CHAR(64),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT config_events_event_type_not_empty
        CHECK (length(trim(event_type)) > 0),

    CONSTRAINT config_events_actor_not_empty
        CHECK (length(trim(actor)) > 0)
);

CREATE INDEX IF NOT EXISTS config_events_document_idx
    ON config_validation.config_events (document_id);

CREATE INDEX IF NOT EXISTS config_events_occurred_at_idx
    ON config_validation.config_events (occurred_at DESC);

DROP TRIGGER IF EXISTS config_events_no_update
    ON config_validation.config_events;

CREATE TRIGGER config_events_no_update
BEFORE UPDATE ON config_validation.config_events
FOR EACH ROW
EXECUTE FUNCTION config_validation.prevent_event_mutation();

DROP TRIGGER IF EXISTS config_events_no_delete
    ON config_validation.config_events;

CREATE TRIGGER config_events_no_delete
BEFORE DELETE ON config_validation.config_events
FOR EACH ROW
EXECUTE FUNCTION config_validation.prevent_event_mutation();

COMMIT;