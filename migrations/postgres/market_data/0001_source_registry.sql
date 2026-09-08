BEGIN;
CREATE SCHEMA IF NOT EXISTS market_data;

DO $$ BEGIN
    CREATE TYPE market_data.provenance_tier AS ENUM ('T0', 'T1', 'T2', 'T3');
    CREATE TYPE market_data.source_role AS ENUM ('CANONICAL', 'VALIDATOR', 'FAILOVER', 'RESEARCH_ONLY');
    CREATE TYPE market_data.data_type AS ENUM ('L1_TICK', 'L2_BOOK', 'OHLCV', 'TRADES', 'LIQUIDATIONS', 'METADATA');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS market_data.sources (
    source_id           TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    tier                market_data.provenance_tier NOT NULL,
    asset_classes       TEXT[] NOT NULL, -- TEXT[] bypasses sqlx enum array macro hell
    is_venue_native     BOOLEAN NOT NULL DEFAULT FALSE,
    provides_sequence_ids BOOLEAN NOT NULL DEFAULT FALSE,
    provides_l2_depth   BOOLEAN NOT NULL DEFAULT FALSE,
    namespace           TEXT NOT NULL DEFAULT 'production',
    trust_score         DOUBLE PRECISION NOT NULL DEFAULT 100.00, -- f64 bypasses rust_decimal hell
    is_healthy          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT sources_tier_namespace_check CHECK (
        (tier IN ('T0', 'T1') AND namespace = 'production') OR
        (tier IN ('T2', 'T3') AND namespace = 'research')
    )
);

CREATE TABLE IF NOT EXISTS market_data.source_assignments (
    assignment_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id           TEXT NOT NULL REFERENCES market_data.sources(source_id) ON DELETE CASCADE,
    asset_class         TEXT NOT NULL, -- Store as TEXT, validate in Rust
    data_type           market_data.data_type NOT NULL,
    role                market_data.source_role NOT NULL,
    priority            INTEGER NOT NULL DEFAULT 100,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT source_assignments_unique_role UNIQUE (source_id, asset_class, data_type, role)
);
CREATE INDEX IF NOT EXISTS idx_source_assignments_lookup ON market_data.source_assignments (asset_class, data_type, role, priority);
COMMIT;
