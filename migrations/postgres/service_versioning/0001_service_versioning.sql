-- ApexQuant Ultra
-- Feature 0.21: Service Versioning
-- PostgreSQL service registry and version lifecycle.

BEGIN;

CREATE SCHEMA IF NOT EXISTS service_versioning;

DO $$
BEGIN
    CREATE TYPE service_versioning.service_version_status AS ENUM (
        'DRAFT',
        'RELEASED',
        'DEPRECATED',
        'RETIRED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE OR REPLACE FUNCTION service_versioning.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION service_versioning.prevent_event_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'service version events are append-only';
END;
$$;

CREATE TABLE IF NOT EXISTS service_versioning.services (
    service_name TEXT PRIMARY KEY,
    plane        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT services_service_name_format
        CHECK (service_name ~ '^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$'),

    CONSTRAINT services_plane_not_empty
        CHECK (length(trim(plane)) > 0)
);

DROP TRIGGER IF EXISTS services_updated_at_trigger
    ON service_versioning.services;

CREATE TRIGGER services_updated_at_trigger
BEFORE UPDATE ON service_versioning.services
FOR EACH ROW
EXECUTE FUNCTION service_versioning.set_updated_at();

CREATE TABLE IF NOT EXISTS service_versioning.service_versions (
    version_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name           TEXT NOT NULL
        REFERENCES service_versioning.services(service_name)
        ON DELETE CASCADE,
    version                TEXT NOT NULL,
    major                  INTEGER NOT NULL,
    minor                  INTEGER NOT NULL,
    patch                  INTEGER NOT NULL,
    prerelease             TEXT,
    build_metadata         TEXT,
    git_sha                TEXT,
    image_tag              TEXT,
    api_version            TEXT NOT NULL DEFAULT 'v1',
    min_compatible_version TEXT,
    status                 service_versioning.service_version_status NOT NULL DEFAULT 'DRAFT',
    checksum_sha256        CHAR(64),
    metadata               JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    released_at            TIMESTAMPTZ,
    deprecated_at          TIMESTAMPTZ,
    retired_at             TIMESTAMPTZ,
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT service_versions_service_name_version_unique
        UNIQUE (service_name, version),

    CONSTRAINT service_versions_major_nonnegative
        CHECK (major >= 0),

    CONSTRAINT service_versions_minor_nonnegative
        CHECK (minor >= 0),

    CONSTRAINT service_versions_patch_nonnegative
        CHECK (patch >= 0),

    CONSTRAINT service_versions_git_sha_format
        CHECK (git_sha IS NULL OR git_sha ~ '^[0-9a-f]{7,40}$'),

    CONSTRAINT service_versions_checksum_format
        CHECK (checksum_sha256 IS NULL OR checksum_sha256 ~ '^[0-9a-f]{64}$'),

    CONSTRAINT service_versions_api_version_not_empty
        CHECK (length(trim(api_version)) > 0)
);

CREATE INDEX IF NOT EXISTS service_versions_service_name_idx
    ON service_versioning.service_versions (service_name);

CREATE INDEX IF NOT EXISTS service_versions_status_idx
    ON service_versioning.service_versions (status);

CREATE INDEX IF NOT EXISTS service_versions_created_at_idx
    ON service_versioning.service_versions (created_at DESC);

DROP TRIGGER IF EXISTS service_versions_updated_at_trigger
    ON service_versioning.service_versions;

CREATE TRIGGER service_versions_updated_at_trigger
BEFORE UPDATE ON service_versioning.service_versions
FOR EACH ROW
EXECUTE FUNCTION service_versioning.set_updated_at();

CREATE TABLE IF NOT EXISTS service_versioning.service_version_dependencies (
    dependency_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id              UUID NOT NULL
        REFERENCES service_versioning.service_versions(version_id)
        ON DELETE CASCADE,
    depends_on_service_name TEXT NOT NULL
        REFERENCES service_versioning.services(service_name)
        ON DELETE RESTRICT,
    min_version             TEXT NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT service_version_dependencies_unique
        UNIQUE (version_id, depends_on_service_name),

    CONSTRAINT service_version_dependencies_min_version_not_empty
        CHECK (length(trim(min_version)) > 0)
);

CREATE INDEX IF NOT EXISTS service_version_dependencies_version_idx
    ON service_versioning.service_version_dependencies (version_id);

CREATE INDEX IF NOT EXISTS service_version_dependencies_service_idx
    ON service_versioning.service_version_dependencies (depends_on_service_name);

CREATE TABLE IF NOT EXISTS service_versioning.service_version_events (
    event_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id UUID NOT NULL
        REFERENCES service_versioning.service_versions(version_id)
        ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    actor      TEXT NOT NULL,
    reason     TEXT,
    details    JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT service_version_events_event_type_not_empty
        CHECK (length(trim(event_type)) > 0),

    CONSTRAINT service_version_events_actor_not_empty
        CHECK (length(trim(actor)) > 0)
);

CREATE INDEX IF NOT EXISTS service_version_events_version_idx
    ON service_versioning.service_version_events (version_id);

CREATE INDEX IF NOT EXISTS service_version_events_occurred_at_idx
    ON service_versioning.service_version_events (occurred_at DESC);

DROP TRIGGER IF EXISTS service_version_events_no_update
    ON service_versioning.service_version_events;

CREATE TRIGGER service_version_events_no_update
BEFORE UPDATE ON service_versioning.service_version_events
FOR EACH ROW
EXECUTE FUNCTION service_versioning.prevent_event_mutation();

DROP TRIGGER IF EXISTS service_version_events_no_delete
    ON service_versioning.service_version_events;

CREATE TRIGGER service_version_events_no_delete
BEFORE DELETE ON service_versioning.service_version_events
FOR EACH ROW
EXECUTE FUNCTION service_versioning.prevent_event_mutation();

COMMIT;