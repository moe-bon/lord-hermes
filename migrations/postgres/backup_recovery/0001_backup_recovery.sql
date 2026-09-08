-- ApexQuant Ultra
-- Feature 0.24: Backup & Recovery Infrastructure
-- PostgreSQL backup policies, runs, artifacts, and restore audit.

BEGIN;

CREATE SCHEMA IF NOT EXISTS backup_recovery;

DO $$
BEGIN
    CREATE TYPE backup_recovery.target_system AS ENUM (
        'POSTGRES',
        'CLICKHOUSE',
        'OBJECT_STORAGE',
        'REDIS'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
    CREATE TYPE backup_recovery.backup_run_status AS ENUM (
        'RUNNING',
        'SUCCEEDED',
        'FAILED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
    CREATE TYPE backup_recovery.artifact_status AS ENUM (
        'ACTIVE',
        'EXPIRED',
        'DELETED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
    CREATE TYPE backup_recovery.restore_status AS ENUM (
        'DRY_RUN',
        'RUNNING',
        'SUCCEEDED',
        'FAILED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE OR REPLACE FUNCTION backup_recovery.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END
$$;

CREATE TABLE IF NOT EXISTS backup_recovery.backup_policies (
    policy_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    TEXT NOT NULL UNIQUE,
    target_system           backup_recovery.target_system NOT NULL,
    target_name             TEXT NOT NULL,
    target_connection_ref   TEXT NOT NULL,
    storage_bucket          TEXT NOT NULL,
    storage_prefix          TEXT NOT NULL DEFAULT 'backups/',
    interval_minutes        INTEGER NOT NULL DEFAULT 1440,
    backup_timeout_seconds  INTEGER NOT NULL DEFAULT 3600,
    retention_count         INTEGER,
    retention_days          INTEGER,
    delete_expired          BOOLEAN NOT NULL DEFAULT FALSE,
    encryption_key_ref      TEXT,
    enabled                 BOOLEAN NOT NULL DEFAULT TRUE,
    next_run_at             TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT backup_policies_name_not_empty
        CHECK (length(trim(name)) > 0),

    CONSTRAINT backup_policies_target_name_not_empty
        CHECK (length(trim(target_name)) > 0),

    CONSTRAINT backup_policies_storage_bucket_not_empty
        CHECK (length(trim(storage_bucket)) > 0),

    CONSTRAINT backup_policies_interval_positive
        CHECK (interval_minutes > 0),

    CONSTRAINT backup_policies_timeout_positive
        CHECK (backup_timeout_seconds > 0),

    CONSTRAINT backup_policies_retention_count_positive
        CHECK (retention_count IS NULL OR retention_count > 0),

    CONSTRAINT backup_policies_retention_days_positive
        CHECK (retention_days IS NULL OR retention_days > 0),

    CONSTRAINT backup_policies_connection_ref_safe
        CHECK (
            target_connection_ref LIKE 'env://%'
            OR target_connection_ref LIKE 'vault://%'
            OR target_connection_ref LIKE 'secret://%'
        )
);

DROP TRIGGER IF EXISTS backup_policies_updated_at_trigger
    ON backup_recovery.backup_policies;

CREATE TRIGGER backup_policies_updated_at_trigger
BEFORE UPDATE ON backup_recovery.backup_policies
FOR EACH ROW
EXECUTE FUNCTION backup_recovery.set_updated_at();

CREATE TABLE IF NOT EXISTS backup_recovery.backup_runs (
    run_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_id             UUID NOT NULL
        REFERENCES backup_recovery.backup_policies(policy_id)
        ON DELETE CASCADE,
    trigger               TEXT NOT NULL DEFAULT 'manual',
    status                backup_recovery.backup_run_status NOT NULL,
    started_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at          TIMESTAMPTZ,
    artifact_uri          TEXT,
    artifact_size_bytes   BIGINT,
    checksum_sha256       CHAR(64),
    error                 TEXT,
    verification_status   TEXT,
    last_verified_at      TIMESTAMPTZ,

    CONSTRAINT backup_runs_trigger_not_empty
        CHECK (length(trim(trigger)) > 0),

    CONSTRAINT backup_runs_checksum_format
        CHECK (checksum_sha256 IS NULL OR checksum_sha256 ~ '^[0-9a-f]{64}$'),

    CONSTRAINT backup_runs_size_nonnegative
        CHECK (artifact_size_bytes IS NULL OR artifact_size_bytes >= 0)
);

CREATE INDEX IF NOT EXISTS backup_runs_policy_idx
    ON backup_recovery.backup_runs (policy_id);

CREATE INDEX IF NOT EXISTS backup_runs_status_idx
    ON backup_recovery.backup_runs (status);

CREATE INDEX IF NOT EXISTS backup_runs_started_at_idx
    ON backup_recovery.backup_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS backup_recovery.backup_artifacts (
    artifact_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id               UUID NOT NULL
        REFERENCES backup_recovery.backup_runs(run_id)
        ON DELETE CASCADE,
    policy_id            UUID NOT NULL
        REFERENCES backup_recovery.backup_policies(policy_id)
        ON DELETE CASCADE,
    target_system        backup_recovery.target_system NOT NULL,
    target_name          TEXT NOT NULL,
    storage_key          TEXT NOT NULL,
    uri                  TEXT NOT NULL,
    size_bytes           BIGINT NOT NULL,
    checksum_sha256      CHAR(64) NOT NULL,
    encryption_key_ref   TEXT,
    status               backup_recovery.artifact_status NOT NULL DEFAULT 'ACTIVE',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at           TIMESTAMPTZ,

    CONSTRAINT backup_artifacts_storage_key_not_empty
        CHECK (length(trim(storage_key)) > 0),

    CONSTRAINT backup_artifacts_uri_not_empty
        CHECK (length(trim(uri)) > 0),

    CONSTRAINT backup_artifacts_size_nonnegative
        CHECK (size_bytes >= 0),

    CONSTRAINT backup_artifacts_checksum_format
        CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS backup_artifacts_policy_idx
    ON backup_recovery.backup_artifacts (policy_id);

CREATE INDEX IF NOT EXISTS backup_artifacts_run_idx
    ON backup_recovery.backup_artifacts (run_id);

CREATE INDEX IF NOT EXISTS backup_artifacts_status_idx
    ON backup_recovery.backup_artifacts (status);

CREATE TABLE IF NOT EXISTS backup_recovery.restore_runs (
    restore_id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    backup_run_id               UUID NOT NULL
        REFERENCES backup_recovery.backup_runs(run_id)
        ON DELETE CASCADE,
    target_connection_ref       TEXT NOT NULL,
    target_connection_redacted  TEXT NOT NULL,
    command_redacted            TEXT,
    status                      backup_recovery.restore_status NOT NULL,
    dry_run                     BOOLEAN NOT NULL DEFAULT TRUE,
    started_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at                TIMESTAMPTZ,
    error                       TEXT,

    CONSTRAINT restore_runs_target_connection_ref_safe
        CHECK (
            target_connection_ref LIKE 'env://%'
            OR target_connection_ref LIKE 'vault://%'
            OR target_connection_ref LIKE 'secret://%'
        )
);

CREATE INDEX IF NOT EXISTS restore_runs_backup_run_idx
    ON backup_recovery.restore_runs (backup_run_id);

CREATE INDEX IF NOT EXISTS restore_runs_status_idx
    ON backup_recovery.restore_runs (status);

COMMIT;