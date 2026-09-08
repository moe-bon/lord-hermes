-- ApexQuant Ultra
-- Feature 0.11: Authentication & Authorization Foundation
-- PostgreSQL principal, credential, permission, revocation, and audit schema.

BEGIN;

CREATE SCHEMA IF NOT EXISTS auth;

DO $$
BEGIN
    CREATE TYPE auth.principal_type AS ENUM (
        'SERVICE',
        'ADMIN',
        'USER'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
    CREATE TYPE auth.credential_type AS ENUM (
        'API_KEY'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
    CREATE TYPE auth.credential_status AS ENUM (
        'ACTIVE',
        'REVOKED',
        'EXPIRED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE OR REPLACE FUNCTION auth.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS auth.principals (
    principal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_name TEXT NOT NULL UNIQUE,
    principal_type auth.principal_type NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT principals_subject_name_not_empty
        CHECK (length(trim(subject_name)) > 0)
);

DROP TRIGGER IF EXISTS auth_principals_updated_at_trigger
    ON auth.principals;

CREATE TRIGGER auth_principals_updated_at_trigger
BEFORE UPDATE ON auth.principals
FOR EACH ROW
EXECUTE FUNCTION auth.set_updated_at();

CREATE TABLE IF NOT EXISTS auth.credentials (
    credential_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    principal_id UUID NOT NULL
        REFERENCES auth.principals(principal_id)
        ON DELETE CASCADE,
    credential_type auth.credential_type NOT NULL,
    identifier TEXT NOT NULL UNIQUE,
    secret_hash TEXT NOT NULL,
    status auth.credential_status NOT NULL DEFAULT 'ACTIVE',
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT credentials_identifier_not_empty
        CHECK (length(trim(identifier)) > 0),

    CONSTRAINT credentials_secret_hash_not_empty
        CHECK (length(trim(secret_hash)) > 0)
);

CREATE INDEX IF NOT EXISTS auth_credentials_principal_id_idx
    ON auth.credentials (principal_id);

CREATE INDEX IF NOT EXISTS auth_credentials_status_idx
    ON auth.credentials (status);

DROP TRIGGER IF EXISTS auth_credentials_updated_at_trigger
    ON auth.credentials;

CREATE TRIGGER auth_credentials_updated_at_trigger
BEFORE UPDATE ON auth.credentials
FOR EACH ROW
EXECUTE FUNCTION auth.set_updated_at();

CREATE TABLE IF NOT EXISTS auth.permission_grants (
    principal_id UUID NOT NULL
        REFERENCES auth.principals(principal_id)
        ON DELETE CASCADE,
    permission TEXT NOT NULL,
    expires_at TIMESTAMPTZ,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (principal_id, permission),

    CONSTRAINT permission_grants_permission_not_empty
        CHECK (length(trim(permission)) > 0)
);

CREATE INDEX IF NOT EXISTS auth_permission_grants_permission_idx
    ON auth.permission_grants (permission);

CREATE TABLE IF NOT EXISTS auth.token_revocations (
    jti TEXT PRIMARY KEY,
    principal_id UUID
        REFERENCES auth.principals(principal_id)
        ON DELETE CASCADE,
    revoked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    reason TEXT NOT NULL DEFAULT '',

    CONSTRAINT token_revocations_jti_not_empty
        CHECK (length(trim(jti)) > 0)
);

CREATE INDEX IF NOT EXISTS auth_token_revocations_expires_at_idx
    ON auth.token_revocations (expires_at DESC);

CREATE TABLE IF NOT EXISTS auth.auth_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    subject_name TEXT NOT NULL,
    principal_type TEXT,
    action TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    request_id TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT auth_events_subject_name_not_empty
        CHECK (length(trim(subject_name)) > 0),

    CONSTRAINT auth_events_action_not_empty
        CHECK (length(trim(action)) > 0),

    CONSTRAINT auth_events_decision_valid
        CHECK (decision IN ('ALLOW', 'DENY', 'SUCCESS', 'FAILURE'))
);

CREATE INDEX IF NOT EXISTS auth_auth_events_occurred_at_idx
    ON auth.auth_events (occurred_at DESC);

CREATE INDEX IF NOT EXISTS auth_auth_events_subject_name_idx
    ON auth.auth_events (subject_name);

CREATE INDEX IF NOT EXISTS auth_auth_events_action_idx
    ON auth.auth_events (action);

CREATE INDEX IF NOT EXISTS auth_auth_events_decision_idx
    ON auth.auth_events (decision);

COMMIT;