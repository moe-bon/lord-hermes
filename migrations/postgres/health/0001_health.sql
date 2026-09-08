-- ApexQuant Ultra
-- Feature 0.17: Health Checks & Service Discovery
-- PostgreSQL service registry and dependency health tracking.

BEGIN;

CREATE SCHEMA IF NOT EXISTS health;

DO $$
BEGIN
    CREATE TYPE health.service_status AS ENUM (
        'STARTING',
        'HEALTHY',
        'DEGRADED',
        'UNHEALTHY',
        'SHUTDOWN'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE TABLE IF NOT EXISTS health.service_registry (
    instance_id     TEXT PRIMARY KEY,
    service_name    TEXT NOT NULL,
    plane           TEXT NOT NULL,
    environment     TEXT NOT NULL,
    version         TEXT NOT NULL,
    endpoint        TEXT NOT NULL,
    status          health.service_status NOT NULL DEFAULT 'STARTING',
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_heartbeat  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT registry_service_name_not_empty CHECK (length(trim(service_name)) > 0),
    CONSTRAINT registry_plane_not_empty CHECK (length(trim(plane)) > 0),
    CONSTRAINT registry_endpoint_not_empty CHECK (length(trim(endpoint)) > 0)
);

CREATE INDEX IF NOT EXISTS health_registry_service_name_idx
    ON health.service_registry (service_name);

CREATE INDEX IF NOT EXISTS health_registry_heartbeat_idx
    ON health.service_registry (last_heartbeat);

CREATE TABLE IF NOT EXISTS health.dependency_checks (
    check_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id     TEXT NOT NULL REFERENCES health.service_registry(instance_id) ON DELETE CASCADE,
    dependency_type TEXT NOT NULL,  -- e.g., 'postgres', 'redis', 'kafka', 's3'
    dependency_name TEXT NOT NULL,
    status          TEXT NOT NULL,  -- 'healthy', 'unhealthy'
    latency_ms      NUMERIC(10, 3),
    error_message   TEXT,
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS health_dependency_checks_instance_idx
    ON health.dependency_checks (instance_id, checked_at DESC);

-- Reap stale instances that haven't heartbeated in 60 seconds
CREATE OR REPLACE FUNCTION health.reap_stale_instances()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    reaped_count INTEGER;
BEGIN
    WITH deleted AS (
        DELETE FROM health.service_registry
        WHERE last_heartbeat < now() - INTERVAL '60 seconds'
          AND status != 'SHUTDOWN'
        RETURNING instance_id
    )
    SELECT COUNT(*) INTO reaped_count FROM deleted;
    
    RETURN reaped_count;
END;
$$;

COMMIT;