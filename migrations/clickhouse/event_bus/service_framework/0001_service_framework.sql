-- ApexQuant Ultra
-- Feature 0.1: System Architecture & Service Framework Core
-- ClickHouse service heartbeat telemetry.

CREATE DATABASE IF NOT EXISTS service_framework;

CREATE TABLE IF NOT EXISTS service_framework.service_heartbeat_events
(
    service_id LowCardinality(String),
    service_name LowCardinality(String),
    environment LowCardinality(String),
    plane LowCardinality(String),
    state LowCardinality(String),
    observed_at DateTime64(3, 'UTC'),
    payload String CODEC(ZSTD(3))
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (service_id, observed_at)
TTL toDateTime(observed_at) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS service_framework.service_registry_snapshots
(
    snapshot_id UUID,
    service_id LowCardinality(String),
    service_name LowCardinality(String),
    version LowCardinality(String),
    environment LowCardinality(String),
    plane LowCardinality(String),
    fail_closed_policy LowCardinality(String),
    state LowCardinality(String),
    capabilities String CODEC(ZSTD(3)),
    permissions String CODEC(ZSTD(3)),
    endpoints String CODEC(ZSTD(3)),
    dependencies String CODEC(ZSTD(3)),
    last_heartbeat_at Nullable(DateTime64(3, 'UTC')),
    created_at DateTime64(3, 'UTC'),
    updated_at DateTime64(3, 'UTC'),
    snapshot_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(snapshot_at)
ORDER BY (service_name, snapshot_at)
TTL toDateTime(snapshot_at) + INTERVAL 365 DAY
SETTINGS index_granularity = 8192;