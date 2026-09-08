-- ApexQuant Ultra
-- Feature 0.5: Secrets & Key Management Foundation
-- PostgreSQL secret metadata, policy, and audit schema.

BEGIN;

CREATE SCHEMA IF NOT EXISTS secrets_management;

DO $$
BEGIN
    CREATE TYPE secrets_management.secret_classification AS ENUM (
        'INFRASTRUCTURE',
        'DATABASE',
        'BROKER',
        'EXECUTION',
        'API',
        'MODEL',
        'KNOWLEDGE',
        'OBSERVABILITY'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
    CREATE TYPE secrets_management.secret_action AS ENUM (
        'READ',
        'WRITE',
        'ROTATE',
        'ADMIN'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
    CREATE TYPE secrets_management.policy_effect AS ENUM (
        'ALLOW',
        'DENY'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
    CREATE TYPE secrets_management.secret_version_status AS ENUM (
        'ACTIVE',
        'REVOKED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE OR REPLACE FUNCTION secrets_management.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS secrets_management.secret_metadata (
    secret_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    classification secrets_management.secret_classification NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    current_version INTEGER NOT NULL DEFAULT 0,
    rotation_interval_days INTEGER,
    expires_at TIMESTAMPTZ,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT secret_metadata_name_not_empty
        CHECK (length(trim(name)) > 0),

    CONSTRAINT secret_metadata_current_version_nonnegative
        CHECK (current_version >= 0),

    CONSTRAINT secret_metadata_rotation_interval_positive
        CHECK (rotation_interval_days IS NULL OR rotation_interval_days > 0)
);

CREATE INDEX IF NOT EXISTS secrets_management_secret_metadata_classification_idx
    ON secrets_management.secret_metadata (classification);

CREATE INDEX IF NOT EXISTS secrets_management_secret_metadata_active_idx
    ON secrets_management.secret_metadata (active);

CREATE INDEX IF NOT EXISTS secrets_management_secret_metadata_expires_at_idx
    ON secrets_management.secret_metadata (expires_at);

DROP TRIGGER IF EXISTS secrets_management_secret_metadata_updated_at_trigger
    ON secrets_management.secret_metadata;

CREATE TRIGGER secrets_management_secret_metadata_updated_at_trigger
BEFORE UPDATE ON secrets_management.secret_metadata
FOR EACH ROW
EXECUTE FUNCTION secrets_management.set_updated_at();

CREATE TABLE IF NOT EXISTS secrets_management.secret_versions (
    version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    secret_id UUID NOT NULL
        REFERENCES secrets_management.secret_metadata(secret_id)
        ON DELETE CASCADE,
    version INTEGER NOT NULL,
    status secrets_management.secret_version_status NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,

    CONSTRAINT secret_versions_unique_per_secret
        UNIQUE (secret_id, version),

    CONSTRAINT secret_versions_version_positive
        CHECK (version > 0)
);

CREATE INDEX IF NOT EXISTS secrets_management_secret_versions_secret_id_idx
    ON secrets_management.secret_versions (secret_id);

CREATE INDEX IF NOT EXISTS secrets_management_secret_versions_status_idx
    ON secrets_management.secret_versions (status);

CREATE TABLE IF NOT EXISTS secrets_management.secret_access_policies (
    policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_service_name TEXT,
    subject_plane TEXT,
    classification secrets_management.secret_classification,
    action secrets_management.secret_action,
    effect secrets_management.policy_effect NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT secret_access_policies_subject_present
        CHECK (
            subject_service_name IS NOT NULL
            OR subject_plane IS NOT NULL
        )
);

CREATE INDEX IF NOT EXISTS secrets_management_policy_subject_plane_idx
    ON secrets_management.secret_access_policies (subject_plane);

CREATE INDEX IF NOT EXISTS secrets_management_policy_service_name_idx
    ON secrets_management.secret_access_policies (subject_service_name);

CREATE INDEX IF NOT EXISTS secrets_management_policy_classification_idx
    ON secrets_management.secret_access_policies (classification);

CREATE INDEX IF NOT EXISTS secrets_management_policy_action_idx
    ON secrets_management.secret_access_policies (action);

CREATE INDEX IF NOT EXISTS secrets_management_policy_effect_idx
    ON secrets_management.secret_access_policies (effect);

CREATE TABLE IF NOT EXISTS secrets_management.secret_access_audit (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    request_id UUID NOT NULL,
    subject_service_name TEXT NOT NULL,
    subject_plane TEXT NOT NULL,
    secret_name TEXT NOT NULL,
    action secrets_management.secret_action NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',

    CONSTRAINT secret_access_audit_decision_valid
        CHECK (decision IN ('ALLOW', 'DENY')),

    CONSTRAINT secret_access_audit_subject_service_not_empty
        CHECK (length(trim(subject_service_name)) > 0),

    CONSTRAINT secret_access_audit_subject_plane_not_empty
        CHECK (length(trim(subject_plane)) > 0),

    CONSTRAINT secret_access_audit_secret_name_not_empty
        CHECK (length(trim(secret_name)) > 0)
);

CREATE INDEX IF NOT EXISTS secrets_management_audit_occurred_at_idx
    ON secrets_management.secret_access_audit (occurred_at DESC);

CREATE INDEX IF NOT EXISTS secrets_management_audit_subject_service_idx
    ON secrets_management.secret_access_audit (subject_service_name);

CREATE INDEX IF NOT EXISTS secrets_management_audit_secret_name_idx
    ON secrets_management.secret_access_audit (secret_name);

CREATE INDEX IF NOT EXISTS secrets_management_audit_action_idx
    ON secrets_management.secret_access_audit (action);

CREATE INDEX IF NOT EXISTS secrets_management_audit_decision_idx
    ON secrets_management.secret_access_audit (decision);

COMMIT;