-- ApexQuant Ultra
-- Feature 0.20: Database Migration Framework
-- ClickHouse migration registry.

CREATE DATABASE IF NOT EXISTS schema_migrations;

CREATE TABLE IF NOT EXISTS schema_migrations.applied_migrations
(
    migration_id    String,
    engine          LowCardinality(String),
    domain          LowCardinality(String),
    version         LowCardinality(String),
    filename        String,
    checksum_sha256 FixedString(64),
    applied_at      DateTime64(3, 'UTC'),
    applied_by      String
)
ENGINE = ReplacingMergeTree(applied_at)
ORDER BY migration_id;

CREATE TABLE IF NOT EXISTS schema_migrations.migration_runs
(
    run_id        UUID,
    engine        LowCardinality(String),
    mode          LowCardinality(String),
    status        LowCardinality(String),
    planned_count UInt32,
    applied_count UInt32,
    skipped_count UInt32,
    failed_count  UInt32,
    error         String,
    started_at    DateTime64(3, 'UTC'),
    completed_at  DateTime64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toDate(started_at)
ORDER BY (started_at, run_id);