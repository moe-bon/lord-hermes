-- ApexQuant Ultra
-- Feature 0.13: Audit Trail Infrastructure
-- ClickHouse analytical audit event store.

CREATE DATABASE IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS audit.events
(
    event_seq       UInt64,
    event_id        UUID,
    occurred_at     DateTime64(3, 'UTC'),
    received_at     DateTime64(3, 'UTC'),

    actor_type      LowCardinality(String),
    actor_id        String,
    principal_name  String,

    service_name    LowCardinality(String),
    plane           LowCardinality(String),

    action          LowCardinality(String),
    resource_type   LowCardinality(String),
    resource_id     String,

    decision        LowCardinality(String),
    reason          String,
    severity        LowCardinality(String),

    request_id      String,
    correlation_id  String,
    trace_id        String,
    idempotency_key String,

    data            String CODEC(ZSTD(3)),

    prev_hash       FixedString(64),
    event_hash      FixedString(64)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (occurred_at, event_seq)
TTL toDateTime(occurred_at) + INTERVAL 730 DAY
SETTINGS index_granularity = 8192;