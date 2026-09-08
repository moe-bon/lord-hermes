-- ApexQuant Ultra
-- Feature 0.8: Event Bus / Message Infrastructure
-- ClickHouse event envelope telemetry.

CREATE DATABASE IF NOT EXISTS event_bus;

CREATE TABLE IF NOT EXISTS event_bus.event_envelopes
(
    event_id UUID,
    event_type LowCardinality(String),
    event_version UInt32,
    occurred_at DateTime64(3, 'UTC'),
    producer_service LowCardinality(String),
    producer_plane LowCardinality(String),
    correlation_id Nullable(UUID),
    causation_id Nullable(UUID),
    idempotency_key String,
    trace_id Nullable(String),
    topic LowCardinality(String),
    payload String CODEC(ZSTD(3)),
    ingested_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (event_type, occurred_at, event_id)
TTL toDateTime(occurred_at) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;