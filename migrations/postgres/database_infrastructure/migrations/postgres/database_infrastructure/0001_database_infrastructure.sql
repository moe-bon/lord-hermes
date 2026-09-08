-- ApexQuant Ultra
-- Feature 0.6: Database Infrastructure
-- PostgreSQL transactional foundation, canonical schemas, and verification audit.

BEGIN;

CREATE SCHEMA IF NOT EXISTS database_infrastructure;

DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS pgcrypto;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'pgcrypto extension not available: %', SQLERRM;
END
$$;

DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'pg_trgm extension not available: %', SQLERRM;
END
$$;

DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS btree_gist;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'btree_gist extension not available: %', SQLERRM;
END
$$;

CREATE SCHEMA IF NOT EXISTS service_framework;
CREATE SCHEMA IF NOT EXISTS container_policy;
CREATE SCHEMA IF NOT EXISTS config_management;
CREATE SCHEMA IF NOT EXISTS secrets_management;
CREATE SCHEMA IF NOT EXISTS market_data;
CREATE SCHEMA IF NOT EXISTS broker;
CREATE SCHEMA IF NOT EXISTS orders;
CREATE SCHEMA IF NOT EXISTS execution;
CREATE SCHEMA IF NOT EXISTS positions;
CREATE SCHEMA IF NOT EXISTS reconciliation;
CREATE SCHEMA IF NOT EXISTS risk;
CREATE SCHEMA IF NOT EXISTS ledger;
CREATE SCHEMA IF NOT EXISTS strategy;
CREATE SCHEMA IF NOT EXISTS features;
CREATE SCHEMA IF NOT EXISTS models;
CREATE SCHEMA IF NOT EXISTS portfolio;
CREATE SCHEMA IF NOT EXISTS knowledge;
CREATE SCHEMA IF NOT EXISTS observability;
CREATE SCHEMA IF NOT EXISTS reporting;

CREATE OR REPLACE FUNCTION database_infrastructure.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS database_infrastructure.database_instances (
    instance_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    environment TEXT NOT NULL,
    cluster_role TEXT NOT NULL DEFAULT 'primary',
    primary_host TEXT NOT NULL,
    port INTEGER NOT NULL,
    database_name TEXT NOT NULL,
    server_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT database_instances_name_not_empty
        CHECK (length(trim(name)) > 0),

    CONSTRAINT database_instances_environment_not_empty
        CHECK (length(trim(environment)) > 0),

    CONSTRAINT database_instances_port_valid
        CHECK (port > 0 AND port <= 65535),

    CONSTRAINT database_instances_database_name_not_empty
        CHECK (length(trim(database_name)) > 0)
);

DROP TRIGGER IF EXISTS database_instances_updated_at_trigger
    ON database_infrastructure.database_instances;

CREATE TRIGGER database_instances_updated_at_trigger
BEFORE UPDATE ON database_infrastructure.database_instances
FOR EACH ROW
EXECUTE FUNCTION database_infrastructure.set_updated_at();

CREATE TABLE IF NOT EXISTS database_infrastructure.schema_registry (
    schema_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    schema_name TEXT NOT NULL UNIQUE,
    domain TEXT NOT NULL,
    ownership_plane TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT schema_registry_schema_name_not_empty
        CHECK (length(trim(schema_name)) > 0),

    CONSTRAINT schema_registry_domain_not_empty
        CHECK (length(trim(domain)) > 0),

    CONSTRAINT schema_registry_ownership_plane_not_empty
        CHECK (length(trim(ownership_plane)) > 0)
);

DROP TRIGGER IF EXISTS schema_registry_updated_at_trigger
    ON database_infrastructure.schema_registry;

CREATE TRIGGER schema_registry_updated_at_trigger
BEFORE UPDATE ON database_infrastructure.schema_registry
FOR EACH ROW
EXECUTE FUNCTION database_infrastructure.set_updated_at();

CREATE TABLE IF NOT EXISTS database_infrastructure.verification_runs (
    run_id TEXT PRIMARY KEY,
    instance_name TEXT NOT NULL,
    environment TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    ok BOOLEAN NOT NULL,
    errors_count INTEGER NOT NULL,
    warnings_count INTEGER NOT NULL,
    report JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT verification_runs_instance_name_not_empty
        CHECK (length(trim(instance_name)) > 0),

    CONSTRAINT verification_runs_environment_not_empty
        CHECK (length(trim(environment)) > 0),

    CONSTRAINT verification_runs_errors_count_nonnegative
        CHECK (errors_count >= 0),

    CONSTRAINT verification_runs_warnings_count_nonnegative
        CHECK (warnings_count >= 0),

    CONSTRAINT verification_runs_started_before_completed
        CHECK (started_at <= completed_at)
);

CREATE INDEX IF NOT EXISTS database_infrastructure_verification_runs_started_at_idx
    ON database_infrastructure.verification_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS database_infrastructure_verification_runs_ok_idx
    ON database_infrastructure.verification_runs (ok);

CREATE INDEX IF NOT EXISTS database_infrastructure_verification_runs_environment_idx
    ON database_infrastructure.verification_runs (environment);

CREATE TABLE IF NOT EXISTS database_infrastructure.verification_checks (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id TEXT NOT NULL
        REFERENCES database_infrastructure.verification_runs(run_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT verification_checks_check_name_not_empty
        CHECK (length(trim(check_name)) > 0),

    CONSTRAINT verification_checks_status_valid
        CHECK (status IN ('PASS', 'WARN', 'FAIL')),

    CONSTRAINT verification_checks_message_not_empty
        CHECK (length(trim(message)) > 0)
);

CREATE INDEX IF NOT EXISTS database_infrastructure_verification_checks_run_id_idx
    ON database_infrastructure.verification_checks (run_id);

CREATE INDEX IF NOT EXISTS database_infrastructure_verification_checks_status_idx
    ON database_infrastructure.verification_checks (status);

CREATE INDEX IF NOT EXISTS database_infrastructure_verification_checks_check_name_idx
    ON database_infrastructure.verification_checks (check_name);

INSERT INTO database_infrastructure.schema_registry (
    schema_name,
    domain,
    ownership_plane,
    description
)
VALUES
    ('service_framework', 'platform', 'CONTROL', 'Service registry and framework metadata'),
    ('container_policy', 'platform', 'CONTROL', 'Containerization policy verification'),
    ('config_management', 'platform', 'CONTROL', 'Environment and configuration management'),
    ('secrets_management', 'security', 'CONTROL', 'Secret metadata and audit'),
    ('database_infrastructure', 'platform', 'CONTROL', 'Database infrastructure verification'),
    ('market_data', 'market_data', 'MARKET_DATA', 'Market data transactional metadata'),
    ('broker', 'broker', 'RISK', 'Broker and exchange account infrastructure'),
    ('orders', 'trading', 'TRADING', 'Order lifecycle state'),
    ('execution', 'trading', 'RISK', 'Execution state and broker transit'),
    ('positions', 'trading', 'RISK', 'Position state'),
    ('reconciliation', 'trading', 'RISK', 'Internal and broker reconciliation'),
    ('risk', 'risk', 'RISK', 'Risk limits, approvals, and circuit breakers'),
    ('ledger', 'ledger', 'CONTROL', 'Financial accounting truth'),
    ('strategy', 'strategy', 'TRADING', 'Strategy registry and lifecycle'),
    ('features', 'research', 'DATA_RESEARCH', 'Feature metadata and governance'),
    ('models', 'ai', 'AI', 'Model metadata and governance'),
    ('portfolio', 'portfolio', 'TRADING', 'Portfolio allocation and exposure'),
    ('knowledge', 'knowledge', 'AI', 'Knowledge ingestion metadata'),
    ('observability', 'observability', 'OBSERVABILITY', 'Operational telemetry metadata'),
    ('reporting', 'reporting', 'CONTROL', 'Reporting metadata')
ON CONFLICT (schema_name) DO NOTHING;

COMMIT;