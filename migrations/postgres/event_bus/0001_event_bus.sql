-- ApexQuant Ultra
-- Feature 0.8: Event Bus / Message Infrastructure
-- PostgreSQL event bus registry, outbox, inbox, and verification audit.

BEGIN;

CREATE SCHEMA IF NOT EXISTS event_bus;

DO $$
BEGIN
    CREATE TYPE event_bus.outbox_status AS ENUM (
        'PENDING',
        'PUBLISHED',
        'FAILED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE TABLE IF NOT EXISTS event_bus.topics (
    topic_name TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    partitions INTEGER NOT NULL,
    replication_factor INTEGER NOT NULL,
    retention_ms BIGINT NOT NULL,
    cleanup_policy TEXT NOT NULL DEFAULT 'delete',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT topics_topic_name_not_empty
        CHECK (length(trim(topic_name)) > 0),

    CONSTRAINT topics_domain_not_empty
        CHECK (length(trim(domain)) > 0),

    CONSTRAINT topics_partitions_positive
        CHECK (partitions > 0),

    CONSTRAINT topics_replication_factor_positive
        CHECK (replication_factor > 0),

    CONSTRAINT topics_retention_ms_nonnegative
        CHECK (retention_ms >= 0),

    CONSTRAINT topics_cleanup_policy_valid
        CHECK (cleanup_policy IN ('delete', 'compact'))
);

CREATE INDEX IF NOT EXISTS event_bus_topics_domain_idx
    ON event_bus.topics (domain);

CREATE TABLE IF NOT EXISTS event_bus.event_outbox (
    outbox_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    topic TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_version INTEGER NOT NULL,
    aggregate_id TEXT,
    idempotency_key TEXT NOT NULL,
    payload JSONB NOT NULL,
    headers JSONB NOT NULL DEFAULT '{}'::jsonb,
    status event_bus.outbox_status NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ,

    CONSTRAINT event_outbox_topic_not_empty
        CHECK (length(trim(topic)) > 0),

    CONSTRAINT event_outbox_event_type_not_empty
        CHECK (length(trim(event_type)) > 0),

    CONSTRAINT event_outbox_event_version_positive
        CHECK (event_version > 0),

    CONSTRAINT event_outbox_idempotency_key_not_empty
        CHECK (length(trim(idempotency_key)) > 0),

    CONSTRAINT event_outbox_attempts_nonnegative
        CHECK (attempts >= 0),

    CONSTRAINT event_outbox_topic_idempotency_key_unique
        UNIQUE (topic, idempotency_key)
);

CREATE INDEX IF NOT EXISTS event_bus_event_outbox_status_idx
    ON event_bus.event_outbox (status);

CREATE INDEX IF NOT EXISTS event_bus_event_outbox_topic_idx
    ON event_bus.event_outbox (topic);

CREATE INDEX IF NOT EXISTS event_bus_event_outbox_created_at_idx
    ON event_bus.event_outbox (created_at);

CREATE TABLE IF NOT EXISTS event_bus.event_inbox (
    event_id UUID NOT NULL,
    consumer_group TEXT NOT NULL,
    topic TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (event_id, consumer_group),

    CONSTRAINT event_inbox_consumer_group_not_empty
        CHECK (length(trim(consumer_group)) > 0),

    CONSTRAINT event_inbox_topic_not_empty
        CHECK (length(trim(topic)) > 0)
);

CREATE INDEX IF NOT EXISTS event_bus_event_inbox_topic_idx
    ON event_bus.event_inbox (topic);

CREATE INDEX IF NOT EXISTS event_bus_event_inbox_processed_at_idx
    ON event_bus.event_inbox (processed_at DESC);

CREATE TABLE IF NOT EXISTS event_bus.verification_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment TEXT NOT NULL,
    bootstrap_servers TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    ok BOOLEAN NOT NULL,
    missing_topics JSONB NOT NULL,
    observed_topics JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT event_bus_verification_environment_not_empty
        CHECK (length(trim(environment)) > 0),

    CONSTRAINT event_bus_verification_bootstrap_servers_not_empty
        CHECK (length(trim(bootstrap_servers)) > 0)
);

CREATE INDEX IF NOT EXISTS event_bus_verification_runs_generated_at_idx
    ON event_bus.verification_runs (generated_at DESC);

CREATE INDEX IF NOT EXISTS event_bus_verification_runs_ok_idx
    ON event_bus.verification_runs (ok);

COMMIT;