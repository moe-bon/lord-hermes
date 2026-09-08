-- ApexQuant Ultra
-- Feature 0.10: API Gateway & Internal API Framework
-- PostgreSQL API gateway route registry and verification audit.

BEGIN;

CREATE SCHEMA IF NOT EXISTS api_gateway;

CREATE OR REPLACE FUNCTION api_gateway.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS api_gateway.services (
    service_name TEXT PRIMARY KEY,
    plane TEXT NOT NULL,
    base_url TEXT NOT NULL,
    environment TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT api_gateway_services_service_name_not_empty
        CHECK (length(trim(service_name)) > 0),

    CONSTRAINT api_gateway_services_plane_not_empty
        CHECK (length(trim(plane)) > 0),

    CONSTRAINT api_gateway_services_base_url_not_empty
        CHECK (length(trim(base_url)) > 0),

    CONSTRAINT api_gateway_services_environment_not_empty
        CHECK (length(trim(environment)) > 0)
);

DROP TRIGGER IF EXISTS api_gateway_services_updated_at_trigger
    ON api_gateway.services;

CREATE TRIGGER api_gateway_services_updated_at_trigger
BEFORE UPDATE ON api_gateway.services
FOR EACH ROW
EXECUTE FUNCTION api_gateway.set_updated_at();

CREATE TABLE IF NOT EXISTS api_gateway.routes (
    route_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name TEXT NOT NULL
        REFERENCES api_gateway.services(service_name)
        ON DELETE CASCADE,
    method TEXT NOT NULL,
    path_prefix TEXT NOT NULL,
    api_version TEXT NOT NULL DEFAULT 'v1',
    auth_required BOOLEAN NOT NULL DEFAULT TRUE,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT api_gateway_routes_unique_route
        UNIQUE (service_name, method, path_prefix, api_version),

    CONSTRAINT api_gateway_routes_service_name_not_empty
        CHECK (length(trim(service_name)) > 0),

    CONSTRAINT api_gateway_routes_method_not_empty
        CHECK (length(trim(method)) > 0),

    CONSTRAINT api_gateway_routes_path_prefix_not_empty
        CHECK (length(trim(path_prefix)) > 0),

    CONSTRAINT api_gateway_routes_api_version_not_empty
        CHECK (length(trim(api_version)) > 0)
);

DROP TRIGGER IF EXISTS api_gateway_routes_updated_at_trigger
    ON api_gateway.routes;

CREATE TRIGGER api_gateway_routes_updated_at_trigger
BEFORE UPDATE ON api_gateway.routes
FOR EACH ROW
EXECUTE FUNCTION api_gateway.set_updated_at();

CREATE TABLE IF NOT EXISTS api_gateway.verification_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    ok BOOLEAN NOT NULL,
    report JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT api_gateway_verification_environment_not_empty
        CHECK (length(trim(environment)) > 0)
);

CREATE INDEX IF NOT EXISTS api_gateway_verification_runs_generated_at_idx
    ON api_gateway.verification_runs (generated_at DESC);

CREATE INDEX IF NOT EXISTS api_gateway_verification_runs_ok_idx
    ON api_gateway.verification_runs (ok);

COMMIT;