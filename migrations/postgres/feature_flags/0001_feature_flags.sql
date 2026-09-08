-- ApexQuant Ultra
-- Feature 0.22 (Rebuilt): Feature Flag System
-- Postgres is the FLAG TRUTH: registry, lifecycle, fail policy, generation,
-- and append-only change events.

BEGIN;

CREATE SCHEMA IF NOT EXISTS feature_flags;

DO $$
BEGIN
    CREATE TYPE feature_flags.flag_status AS ENUM (
        'DRAFT', 'ACTIVE', 'DISABLED', 'RETIRED'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE feature_flags.flag_type AS ENUM (
        'BOOLEAN', 'PERCENTAGE', 'ALLOWLIST', 'DENYLIST'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE feature_flags.flag_class AS ENUM (
        'SAFETY_CRITICAL',   -- fail_value locked false, immutable; 1s staleness
        'TRADING_BEHAVIOR',  -- strategy/model gates; 5s staleness
        'STANDARD'           -- everything else; 60s staleness
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE OR REPLACE FUNCTION feature_flags.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION feature_flags.prevent_event_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'feature flag events are append-only';
END $$;

-- ---------------------------------------------------------------------------
-- Flag registry. One row per flag. generation increments on every committed
-- change so units of work can pin a consistent snapshot.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feature_flags.flags (
    flag_key           TEXT PRIMARY KEY,
    description        TEXT NOT NULL,
    owner              TEXT NOT NULL,

    flag_type          feature_flags.flag_type   NOT NULL,
    flag_class         feature_flags.flag_class  NOT NULL DEFAULT 'STANDARD',
    status             feature_flags.flag_status NOT NULL DEFAULT 'DRAFT',

    -- The positive value the flag carries when ACTIVE and evaluation succeeds.
    bool_value         BOOLEAN,
    rollout_bps        INTEGER NOT NULL DEFAULT 0,
    allowlist          TEXT[] NOT NULL DEFAULT '{}',
    denylist           TEXT[] NOT NULL DEFAULT '{}',
    environments       TEXT[] NOT NULL DEFAULT '{}',  -- empty = all environments

    -- The SAFE state returned on any failure / non-target / staleness breach.
    -- Locked false and immutable for SAFETY_CRITICAL flags (trigger-enforced).
    fail_value         BOOLEAN NOT NULL DEFAULT FALSE,

    -- Monotonically increasing; bumps on every committed change.
    generation         BIGINT NOT NULL DEFAULT 1,

    -- Anti-zombie machinery (Approach A graft).
    review_at          TIMESTAMPTZ NOT NULL,
    expires_at         TIMESTAMPTZ,
    last_evaluated_at  TIMESTAMPTZ,

    -- Governance.
    required_authority TEXT NOT NULL DEFAULT 'flags:write',

    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT flags_key_format
        CHECK (flag_key ~ '^[a-z0-9]([a-z0-9_.-]{0,126}[a-z0-9])?$'),
    CONSTRAINT flags_description_not_empty
        CHECK (length(trim(description)) > 0),
    CONSTRAINT flags_owner_not_empty
        CHECK (length(trim(owner)) > 0),
    CONSTRAINT flags_rollout_bps_valid
        CHECK (rollout_bps >= 0 AND rollout_bps <= 10000),
    CONSTRAINT flags_generation_positive
        CHECK (generation >= 1),
    CONSTRAINT flags_positive_polarity
        -- Negative-polarity names are banned; a disable_X flag is a bug.
        CHECK (flag_key NOT LIKE 'disable\_%' AND flag_key NOT LIKE 'no\_%')
);

CREATE INDEX IF NOT EXISTS feature_flags_flags_status_idx
    ON feature_flags.flags (status);
CREATE INDEX IF NOT EXISTS feature_flags_flags_review_at_idx
    ON feature_flags.flags (review_at);
CREATE INDEX IF NOT EXISTS feature_flags_flags_class_idx
    ON feature_flags.flags (flag_class);

DROP TRIGGER IF EXISTS feature_flags_flags_updated_at_trigger
    ON feature_flags.flags;
CREATE TRIGGER feature_flags_flags_updated_at_trigger
BEFORE UPDATE ON feature_flags.flags
FOR EACH ROW EXECUTE FUNCTION feature_flags.set_updated_at();

-- ---------------------------------------------------------------------------
-- SAFETY_CRITICAL invariants, enforced in the DB so no application path can
-- bypass them:
--   * fail_value is locked FALSE and immutable.
--   * generation can only increase.
--   * RETIRED is terminal (cannot move back to any other status).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION feature_flags.enforce_safety_invariants()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.flag_class = 'SAFETY_CRITICAL' AND NEW.fail_value <> FALSE THEN
        RAISE EXCEPTION
            'SAFETY_CRITICAL flag % must have fail_value locked to false',
            NEW.flag_key;
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF NEW.generation < OLD.generation THEN
            RAISE EXCEPTION 'flag generation must be monotonically increasing';
        END IF;

        IF OLD.status = 'RETIRED' AND NEW.status <> 'RETIRED' THEN
            RAISE EXCEPTION
                'RETIRED flag % is terminal and cannot be reactivated',
                NEW.flag_key;
        END IF;

        IF OLD.flag_class = 'SAFETY_CRITICAL'
           AND NEW.fail_value <> OLD.fail_value THEN
            RAISE EXCEPTION
                'SAFETY_CRITICAL flag % fail_value is immutable',
                NEW.flag_key;
        END IF;
    END IF;

    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS feature_flags_flags_safety_invariants
    ON feature_flags.flags;
CREATE TRIGGER feature_flags_flags_safety_invariants
BEFORE INSERT OR UPDATE ON feature_flags.flags
FOR EACH ROW EXECUTE FUNCTION feature_flags.enforce_safety_invariants();

-- ---------------------------------------------------------------------------
-- Append-only change/audit events. Every mutation records actor + reason and,
-- for rollout increases, the canary step (Approach A governance graft).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feature_flags.flag_events (
    event_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flag_key       TEXT NOT NULL REFERENCES feature_flags.flags(flag_key) ON DELETE CASCADE,
    generation     BIGINT NOT NULL,
    event_type     TEXT NOT NULL,      -- CREATED/ACTIVATED/UPDATED/ROLLOUT_STEP/DISABLED/RETIRED/RECONCILED
    actor          TEXT NOT NULL,
    reason         TEXT NOT NULL,
    authority      TEXT NOT NULL,
    before_state   JSONB,
    after_state    JSONB,
    occurred_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT flag_events_event_type_not_empty
        CHECK (length(trim(event_type)) > 0),
    CONSTRAINT flag_events_actor_not_empty
        CHECK (length(trim(actor)) > 0),
    CONSTRAINT flag_events_reason_not_empty
        CHECK (length(trim(reason)) > 0)
);

CREATE INDEX IF NOT EXISTS feature_flags_events_flag_key_idx
    ON feature_flags.flag_events (flag_key);
CREATE INDEX IF NOT EXISTS feature_flags_events_occurred_at_idx
    ON feature_flags.flag_events (occurred_at DESC);

DROP TRIGGER IF EXISTS feature_flags_events_no_update
    ON feature_flags.flag_events;
CREATE TRIGGER feature_flags_events_no_update
BEFORE UPDATE ON feature_flags.flag_events
FOR EACH ROW EXECUTE FUNCTION feature_flags.prevent_event_mutation();

DROP TRIGGER IF EXISTS feature_flags_events_no_delete
    ON feature_flags.flag_events;
CREATE TRIGGER feature_flags_events_no_delete
BEFORE DELETE ON feature_flags.flag_events
FOR EACH ROW EXECUTE FUNCTION feature_flags.prevent_event_mutation();

-- ---------------------------------------------------------------------------
-- Baked-in, version-pinned defaults used for cold start (Decision #1).
-- Keyed by service_version (0.21) so a deployed binary boots on the exact
-- defaults it was built/tested against, even with Postgres+Redis down.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feature_flags.baked_defaults (
    service_version TEXT NOT NULL,
    flag_key        TEXT NOT NULL REFERENCES feature_flags.flags(flag_key) ON DELETE CASCADE,
    default_value   BOOLEAN NOT NULL,
    pinned_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (service_version, flag_key)
);

COMMIT;