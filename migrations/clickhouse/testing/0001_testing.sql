-- ApexQuant Ultra
-- Feature 0.19: Automated Testing Framework
-- ClickHouse analytical test result store.

CREATE DATABASE IF NOT EXISTS testing;

CREATE TABLE IF NOT EXISTS testing.test_result_events
(
    run_id         UUID,
    suite          LowCardinality(String),
    name           String,
    status         LowCardinality(String),
    duration_ms    Float64,
    environment    LowCardinality(String),
    git_sha        String,
    failure_mode   String,
    inserted_at    DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toDate(inserted_at)
ORDER BY (inserted_at, suite, name)
TTL toDate(inserted_at) + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;