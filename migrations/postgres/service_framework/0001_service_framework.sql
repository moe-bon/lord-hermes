-- ApexQuant Ultra
-- Feature 0.1: System Architecture & Service Framework Core
-- PostgreSQL transactional service registry.

BEGIN;

CREATE SCHEMA IF NOT EXISTS service_framework;

DO $$
BEGIN
    CREATE TYPE service_framework.service_plane AS ENUM (
        'CONTROL',
        'MARKET_DATA',
        'TRADING',
        'RISK',
        'AI',
        'DATA_RESEARCH',
        'OBSERVABILITY'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
    CREATE TYPE service_framework.service_state AS ENUM (
        'STARTING',
        'READY',
        'DEGRADED',
        'STOPPING',
        'FAILED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
    CREATE TYPE service_framework.fail_closed_policy AS ENUM (
        'READ_ONLY',
        'CANCEL_OPEN_ORDERS',
        'HALT_TRADING',
        'SHUTDOWN'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE OR REPLACE FUNCTION service_framework.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS service_framework.service_registry (
    service_id TEXT PRIMARY KEY,
    service_name TEXT NOT NULL,
    version TEXT NOT NULL,
    environment TEXT NOT NULL,
    plane service_framework.service_plane NOT NULL,
    fail_closed_policy service_framework.fail_closed_policy NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
    permissions JSONB NOT NULL DEFAULT '[]'::jsonb,
    endpoints JSONB NOT NULL DEFAULT '[]'::jsonb,
    dependencies JSONB NOT NULL DEFAULT '[]'::jsonb,
    state service_framework.service_state NOT NULL DEFAULT 'STARTING',
    last_heartbeat_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT service_registry_unique_name_version_environment
        UNIQUE (service_name, version, environment),

    CONSTRAINT service_registry_service_name_not_empty
        CHECK (length(trim(service_name)) > 0),

    CONSTRAINT service_registry_version_not_empty
        CHECK (length(trim(version)) > 0),

    CONSTRAINT service_registry_environment_not_empty
        CHECK (length(trim(environment)) > 0),

    CONSTRAINT service_registry_service_id_not_empty
        CHECK (length(trim(service_id)) > 0)
);

CREATE INDEX IF NOT EXISTS service_registry_environment_idx
    ON service_framework.service_registry (environment);

CREATE INDEX IF NOT EXISTS service_registry_plane_idx
    ON service_framework.service_registry (plane);

CREATE INDEX IF NOT EXISTS service_registry_state_idx
    ON service_framework.service_registry (state);

CREATE INDEX IF NOT EXISTS service_registry_last_heartbeat_idx
    ON service_framework.service_registry (last_heartbeat_at);

CREATE INDEX IF NOT EXISTS service_registry_capabilities_gin_idx
    ON service_framework.service_registry USING gin (capabilities);

CREATE INDEX IF NOT EXISTS service_registry_permissions_gin_idx
    ON service_framework.service_registry USING gin (permissions);

CREATE INDEX IF NOT EXISTS service_registry_endpoints_gin_idx
    ON service_framework.service_registry USING gin (endpoints);

CREATE INDEX IF NOT EXISTS service_registry_dependencies_gin_idx
    ON service_framework.service_registry USING gin (dependencies);

DROP TRIGGER IF EXISTS service_registry_updated_at_trigger
    ON service_framework.service_registry;

CREATE TRIGGER service_registry_updated_at_trigger
BEFORE UPDATE ON service_framework.service_registry
FOR EACH ROW
EXECUTE FUNCTION service_framework.set_updated_at();

CREATE TABLE IF NOT EXISTS service_framework.service_heartbeat_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY,
    service_id TEXT NOT NULL
        REFERENCES service_framework.service_registry(service_id)
        ON DELETE CASCADE,
    state service_framework.service_state NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,

    PRIMARY KEY (id, observed_at)
) PARTITION BY RANGE (observed_at);

CREATE TABLE IF NOT EXISTS service_framework.service_heartbeat_log_default
    PARTITION OF service_framework.service_heartbeat_log DEFAULT;

CREATE INDEX IF NOT EXISTS service_heartbeat_log_service_observed_idx
    ON service_framework.service_heartbeat_log (service_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS service_heartbeat_log_observed_idx
    ON service_framework.service_heartbeat_log (observed_at DESC);

COMMIT;

