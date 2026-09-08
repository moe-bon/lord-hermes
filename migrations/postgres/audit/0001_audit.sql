-- ApexQuant Ultra
-- Feature 0.13: Audit Trail Infrastructure
-- Append-only, hash-chained audit event log.

BEGIN;

CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS audit.events (
    event_seq        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id         UUID NOT NULL UNIQUE,
    occurred_at      TIMESTAMPTZ NOT NULL,
    received_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    actor_type       TEXT NOT NULL,
    actor_id         TEXT,
    principal_name   TEXT,

    service_name     TEXT NOT NULL,
    plane            TEXT NOT NULL,

    action           TEXT NOT NULL,
    resource_type    TEXT NOT NULL DEFAULT '',
    resource_id      TEXT NOT NULL DEFAULT '',

    decision         TEXT NOT NULL DEFAULT 'INFO',
    reason           TEXT NOT NULL DEFAULT '',
    severity         TEXT NOT NULL DEFAULT 'INFO',

    request_id       TEXT,
    correlation_id   TEXT,
    trace_id         TEXT,
    idempotency_key  TEXT,

    data             JSONB NOT NULL DEFAULT '{}'::jsonb,

    prev_hash        CHAR(64) NOT NULL,
    event_hash       CHAR(64) NOT NULL,

    CONSTRAINT audit_events_actor_type_valid
        CHECK (actor_type IN ('SERVICE', 'USER', 'SYSTEM')),

    CONSTRAINT audit_events_decision_valid
        CHECK (decision IN ('ALLOW', 'DENY', 'SUCCESS', 'FAILURE', 'INFO')),

    CONSTRAINT audit_events_severity_valid
        CHECK (severity IN ('DEBUG', 'INFO', 'WARNING', 'CRITICAL')),

    CONSTRAINT audit_events_service_name_not_empty
        CHECK (length(trim(service_name)) > 0),

    CONSTRAINT audit_events_plane_not_empty
        CHECK (length(trim(plane)) > 0),

    CONSTRAINT audit_events_action_not_empty
        CHECK (length(trim(action)) > 0),

    CONSTRAINT audit_events_hash_format_valid
        CHECK (event_hash ~ '^[0-9a-f]{64}$'),

    CONSTRAINT audit_events_prev_hash_format_valid
        CHECK (prev_hash ~ '^[0-9a-f]{64}$')
);

CREATE UNIQUE INDEX IF NOT EXISTS audit_events_idempotency_uq
    ON audit.events (service_name, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS audit_events_occurred_at_idx
    ON audit.events (occurred_at DESC);

CREATE INDEX IF NOT EXISTS audit_events_service_idx
    ON audit.events (service_name, occurred_at DESC);

CREATE INDEX IF NOT EXISTS audit_events_action_idx
    ON audit.events (action, occurred_at DESC);

CREATE INDEX IF NOT EXISTS audit_events_actor_idx
    ON audit.events (actor_type, actor_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS audit_events_request_id_idx
    ON audit.events (request_id);

CREATE INDEX IF NOT EXISTS audit_events_resource_idx
    ON audit.events (resource_type, resource_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS audit.event_delivery (
    event_seq     BIGINT PRIMARY KEY
        REFERENCES audit.events(event_seq)
        ON DELETE RESTRICT,
    published_at  TIMESTAMPTZ,
    attempts      INTEGER NOT NULL DEFAULT 0,
    last_error    TEXT,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audit_event_delivery_unpublished_idx
    ON audit.event_delivery (event_seq)
    WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS audit.integrity_checks (
    check_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at   TIMESTAMPTZ,
    start_seq      BIGINT,
    end_seq        BIGINT,
    events_checked INTEGER NOT NULL DEFAULT 0,
    ok             BOOLEAN NOT NULL,
    violations     JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS audit_integrity_checks_started_at_idx
    ON audit.integrity_checks (started_at DESC);

CREATE INDEX IF NOT EXISTS audit_integrity_checks_ok_idx
    ON audit.integrity_checks (ok);

-- ===========================================================================
-- Append-only enforcement
-- ===========================================================================

CREATE OR REPLACE FUNCTION audit.prevent_audit_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'audit events are immutable';
END;
$$;

DROP TRIGGER IF EXISTS audit_events_no_update ON audit.events;
CREATE TRIGGER audit_events_no_update
BEFORE UPDATE ON audit.events
FOR EACH ROW
EXECUTE FUNCTION audit.prevent_audit_mutation();

DROP TRIGGER IF EXISTS audit_events_no_delete ON audit.events;
CREATE TRIGGER audit_events_no_delete
BEFORE DELETE ON audit.events
FOR EACH ROW
EXECUTE FUNCTION audit.prevent_audit_mutation();

DROP TRIGGER IF EXISTS audit_events_no_truncate ON audit.events;
CREATE TRIGGER audit_events_no_truncate
BEFORE TRUNCATE ON audit.events
FOR EACH STATEMENT
EXECUTE FUNCTION audit.prevent_audit_mutation();

COMMIT;