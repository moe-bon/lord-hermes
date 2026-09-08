BEGIN;

-- Tracks the real-time health and backoff state of the Rust Ingestion Fleet
CREATE TABLE IF NOT EXISTS market_data.connector_state (
    source_id           TEXT PRIMARY KEY REFERENCES market_data.sources(source_id),
    status              TEXT NOT NULL DEFAULT 'STOPPED', -- RUNNING, STOPPED, ERROR, BACKOFF
    last_sequence_id    TEXT,
    last_fetch_ts_ns    BIGINT,
    reconnect_count     INTEGER NOT NULL DEFAULT 0,
    last_error          TEXT,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Append-only audit trail for ingestion anomalies (Law #4 enforcement)
CREATE TABLE IF NOT EXISTS market_data.ingest_audit_events (
    event_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id           TEXT NOT NULL,
    event_type          TEXT NOT NULL, -- CONNECTED, DISCONNECTED, GAP_DETECTED, DUPLICATE_DETECTED, GARBAGE_DATA
    severity            TEXT NOT NULL DEFAULT 'INFO',
    details             JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ingest_audit_source ON market_data.ingest_audit_events(source_id, occurred_at DESC);

COMMIT;