-- ApexQuant Ultra
-- Feature 0.21: Service Versioning
-- ClickHouse analytical service-version event store.

CREATE DATABASE IF NOT EXISTS service_versioning;

CREATE TABLE IF NOT EXISTS service_versioning.service_version_events
(
    event_id    UUID,
    service     LowCardinality(String),
    version     LowCardinality(String),
    status      LowCardinality(String),
    event_type  LowCardinality(String),
    actor       String,
    reason      String,
    details     String CODEC(ZSTD(3)),
    occurred_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toDate(occurred_at)
ORDER BY (occurred_at, service, version)
TTL toDate(occurred_at) + INTERVAL 365 DAY
SETTINGS index_granularity = 8192;