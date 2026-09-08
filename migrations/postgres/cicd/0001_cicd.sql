-- ApexQuant Ultra
-- Feature 0.18: CI/CD Pipeline
-- PostgreSQL deployment tracking and version management.

BEGIN;

CREATE SCHEMA IF NOT EXISTS cicd;

DO $$
BEGIN
    CREATE TYPE cicd.deployment_status AS ENUM (
        'PENDING',
        'BUILDING',
        'TESTING',
        'SCANNING',
        'SIGNING',
        'PUSHING',
        'DEPLOYING',
        'HEALTH_CHECK',
        'ACTIVE',
        'ROLLING_BACK',
        'ROLLED_BACK',
        'FAILED',
        'CANCELLED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
    CREATE TYPE cicd.environment_name AS ENUM (
        'local',
        'sandbox',
        'paper',
        'shadow',
        'production'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE TABLE IF NOT EXISTS cicd.pipelines (
    pipeline_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name    TEXT NOT NULL,
    git_branch      TEXT NOT NULL,
    git_sha         TEXT NOT NULL,
    version         TEXT NOT NULL,
    triggered_by    TEXT NOT NULL,
    status          cicd.deployment_status NOT NULL DEFAULT 'PENDING',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT pipelines_service_name_not_empty
        CHECK (length(trim(service_name)) > 0),

    CONSTRAINT pipelines_git_sha_format
        CHECK (git_sha ~ '^[0-9a-f]{7,40}$'),

    CONSTRAINT pipelines_version_format
        CHECK (version ~ '^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$')
);

CREATE INDEX IF NOT EXISTS cicd_pipelines_service_idx
    ON cicd.pipelines (service_name, started_at DESC);

CREATE INDEX IF NOT EXISTS cicd_pipelines_status_idx
    ON cicd.pipelines (status);

CREATE TABLE IF NOT EXISTS cicd.pipeline_stages (
    stage_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id     UUID NOT NULL REFERENCES cicd.pipelines(pipeline_id) ON DELETE CASCADE,
    stage_name      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'PENDING',
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    output          JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT pipeline_stages_name_not_empty
        CHECK (length(trim(stage_name)) > 0)
);

CREATE INDEX IF NOT EXISTS cicd_pipeline_stages_pipeline_idx
    ON cicd.pipeline_stages (pipeline_id);

CREATE TABLE IF NOT EXISTS cicd.deployments (
    deployment_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id     UUID NOT NULL REFERENCES cicd.pipelines(pipeline_id),
    service_name    TEXT NOT NULL,
    environment     cicd.environment_name NOT NULL,
    version         TEXT NOT NULL,
    image_tag       TEXT NOT NULL,
    git_sha         TEXT NOT NULL,
    status          cicd.deployment_status NOT NULL DEFAULT 'DEPLOYING',
    deployed_by     TEXT NOT NULL,
    deployed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    rolled_back_at  TIMESTAMPTZ,
    rollback_reason TEXT,
    health_check    JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT deployments_service_name_not_empty
        CHECK (length(trim(service_name)) > 0),

    CONSTRAINT deployments_version_not_empty
        CHECK (length(trim(version)) > 0)
);

CREATE INDEX IF NOT EXISTS cicd_deployments_service_env_idx
    ON cicd.deployments (service_name, environment, deployed_at DESC);

CREATE INDEX IF NOT EXISTS cicd_deployments_status_idx
    ON cicd.deployments (status);

CREATE TABLE IF NOT EXISTS cicd.version_locks (
    lock_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name    TEXT NOT NULL,
    environment     cicd.environment_name NOT NULL,
    version         TEXT NOT NULL,
    image_tag       TEXT NOT NULL,
    git_sha         TEXT NOT NULL,
    locked_by       TEXT NOT NULL,
    locked_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT version_locks_service_env_unique
        UNIQUE (service_name, environment, is_active)
);

CREATE UNIQUE INDEX IF NOT EXISTS cicd_version_locks_active_uq
    ON cicd.version_locks (service_name, environment)
    WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS cicd.scan_results (
    scan_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id     UUID NOT NULL REFERENCES cicd.pipelines(pipeline_id) ON DELETE CASCADE,
    scan_type       TEXT NOT NULL,
    scanner         TEXT NOT NULL,
    status          TEXT NOT NULL,
    findings_count  INTEGER NOT NULL DEFAULT 0,
    critical_count  INTEGER NOT NULL DEFAULT 0,
    high_count      INTEGER NOT NULL DEFAULT 0,
    medium_count    INTEGER NOT NULL DEFAULT 0,
    low_count       INTEGER NOT NULL DEFAULT 0,
    report_url      TEXT,
    scanned_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    details         JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT scan_results_scan_type_not_empty
        CHECK (length(trim(scan_type)) > 0),

    CONSTRAINT scan_results_scanner_not_empty
        CHECK (length(trim(scanner)) > 0)
);

CREATE INDEX IF NOT EXISTS cicd_scan_results_pipeline_idx
    ON cicd.scan_results (pipeline_id);

COMMIT;