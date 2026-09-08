-- ApexQuant Ultra
-- Feature 0.14: Structured Logging Infrastructure
-- ClickHouse structured log storage.

CREATE DATABASE IF NOT EXISTS logging;

CREATE TABLE IF NOT EXISTS logging.structured_logs
(
    ts             DateTime64(3, 'UTC'),
    level          LowCardinality(String),
    service        LowCardinality(String),
    service_version LowCardinality(String),
    environment    LowCardinality(String),
    plane          LowCardinality(String),
    event          LowCardinality(String),
    message        String,
    trace_id       String,
    request_id     String,
    correlation_id String,
    actor_id       String,
    data           String CODEC(ZSTD(3))
)
ENGINE = MergeTree
PARTITION BY toDate(ts)
ORDER BY (service, ts, event)
TTL toDate(ts) + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;