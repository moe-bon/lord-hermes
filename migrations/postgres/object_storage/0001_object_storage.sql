-- ApexQuant Ultra
-- Feature 0.9: Object Storage Infrastructure
-- PostgreSQL object storage registry and reference metadata.

BEGIN;

CREATE SCHEMA IF NOT EXISTS object_storage;

DO $$
BEGIN
    CREATE TYPE object_storage.bucket_purpose AS ENUM (
        'MARKET_DATA_RAW',
        'MODEL_ARTIFACTS',
        'KNOWLEDGE_RAW',
        'BACKUPS',
        'TEMPORARY'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE TABLE IF NOT EXISTS object_storage.buckets (
    bucket_name TEXT PRIMARY KEY,
    environment TEXT NOT NULL,
    purpose object_storage.bucket_purpose NOT NULL,
    versioning_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    lifecycle_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT buckets_environment_not_empty
        CHECK (length(trim(environment)) > 0)
);

CREATE INDEX IF NOT EXISTS object_storage_buckets_environment_idx
    ON object_storage.buckets (environment);

CREATE INDEX IF NOT EXISTS object_storage_buckets_purpose_idx
    ON object_storage.buckets (purpose);

CREATE TABLE IF NOT EXISTS object_storage.object_references (
    reference_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bucket_name TEXT NOT NULL
        REFERENCES object_storage.buckets(bucket_name)
        ON DELETE RESTRICT,
    object_key TEXT NOT NULL,
    version_id TEXT,
    content_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    checksum_sha256 TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT object_references_object_key_not_empty
        CHECK (length(trim(object_key)) > 0),

    CONSTRAINT object_references_size_bytes_nonnegative
        CHECK (size_bytes >= 0)
);

CREATE INDEX IF NOT EXISTS object_storage_references_bucket_key_idx
    ON object_storage.object_references (bucket_name, object_key);

CREATE INDEX IF NOT EXISTS object_storage_references_created_at_idx
    ON object_storage.object_references (created_at DESC);

CREATE TABLE IF NOT EXISTS object_storage.verification_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    ok BOOLEAN NOT NULL,
    missing_buckets JSONB NOT NULL,
    observed_buckets JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS object_storage_verification_runs_generated_at_idx
    ON object_storage.verification_runs (generated_at DESC);

COMMIT;