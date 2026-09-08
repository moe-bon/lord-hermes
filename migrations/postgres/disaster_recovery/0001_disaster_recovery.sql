-- ApexQuant Ultra
-- Feature 0.25: Disaster Recovery Foundation
-- PostgreSQL disaster recovery plans, components, drills, and audit events.

BEGIN;

CREATE SCHEMA IF NOT EXISTS disaster_recovery;

CREATE OR REPLACE FUNCTION disaster_recovery.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION disaster_recovery.prevent_event_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'disaster recovery events are append-only';
END
$$;

CREATE TABLE IF NOT EXISTS disaster_recovery.recovery_plans (
    plan_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL UNIQUE,
    environment         TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    criticality_tier    TEXT NOT NULL DEFAULT 'TIER_1',
    rpo_seconds         INTEGER NOT NULL,
    rto_seconds         INTEGER NOT NULL,
    drill_max_age_days  INTEGER,
    status              TEXT NOT NULL DEFAULT 'DRAFT',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT recovery_plans_name_not_empty
        CHECK (length(trim(name)) > 0),

    CONSTRAINT recovery_plans_environment_not_empty
        CHECK (length(trim(environment)) > 0),

    CONSTRAINT recovery_plans_criticality_tier_valid
        CHECK (criticality_tier IN ('TIER_1', 'TIER_2', 'TIER_3')),

    CONSTRAINT recovery_plans_rpo_positive
        CHECK (rpo_seconds > 0),

    CONSTRAINT recovery_plans_rto_positive
        CHECK (rto_seconds > 0),

    CONSTRAINT recovery_plans_drill_max_age_positive
        CHECK (drill_max_age_days IS NULL OR drill_max_age_days > 0),

    CONSTRAINT recovery_plans_status_valid
        CHECK (status IN ('DRAFT', 'ACTIVE', 'RETIRED'))
);

DROP TRIGGER IF EXISTS recovery_plans_updated_at_trigger
    ON disaster_recovery.recovery_plans;

CREATE TRIGGER recovery_plans_updated_at_trigger
BEFORE UPDATE ON disaster_recovery.recovery_plans
FOR EACH ROW
EXECUTE FUNCTION disaster_recovery.set_updated_at();

CREATE TABLE IF NOT EXISTS disaster_recovery.recovery_components (
    component_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id               UUID NOT NULL
        REFERENCES disaster_recovery.recovery_plans(plan_id)
        ON DELETE CASCADE,
    component_name        TEXT NOT NULL,
    component_type        TEXT NOT NULL,
    recovery_strategy     TEXT NOT NULL,
    priority              INTEGER NOT NULL DEFAULT 100,
    backup_policy_name    TEXT,
    health_endpoint       TEXT,
    rpo_seconds           INTEGER,
    rto_seconds           INTEGER,
    notes                 TEXT NOT NULL DEFAULT '',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT recovery_components_component_name_not_empty
        CHECK (length(trim(component_name)) > 0),

    CONSTRAINT recovery_components_component_type_valid
        CHECK (
            component_type IN (
                'SERVICE',
                'DATABASE',
                'EVENT_BUS',
                'OBJECT_STORAGE',
                'REDIS',
                'CONFIG'
            )
        ),

    CONSTRAINT recovery_components_recovery_strategy_valid
        CHECK (
            recovery_strategy IN (
                'RESTORE_FROM_BACKUP',
                'RESTART',
                'REBUILD',
                'FAILOVER',
                'MANUAL'
            )
        ),

    CONSTRAINT recovery_components_priority_positive
        CHECK (priority > 0),

    CONSTRAINT recovery_components_rpo_positive
        CHECK (rpo_seconds IS NULL OR rpo_seconds > 0),

    CONSTRAINT recovery_components_rto_positive
        CHECK (rto_seconds IS NULL OR rto_seconds > 0),

    CONSTRAINT recovery_components_plan_component_unique
        UNIQUE (plan_id, component_name)
);

CREATE INDEX IF NOT EXISTS recovery_components_plan_idx
    ON disaster_recovery.recovery_components (plan_id);

CREATE TABLE IF NOT EXISTS disaster_recovery.dr_drills (
    drill_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id           UUID NOT NULL
        REFERENCES disaster_recovery.recovery_plans(plan_id)
        ON DELETE CASCADE,
    environment       TEXT NOT NULL,
    trigger           TEXT NOT NULL DEFAULT 'manual',
    actor             TEXT NOT NULL DEFAULT 'system',
    status            TEXT NOT NULL DEFAULT 'RUNNING',
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at      TIMESTAMPTZ,
    readiness_score   NUMERIC(5,2),
    result            JSONB NOT NULL DEFAULT '{}'::jsonb,
    error             TEXT,

    CONSTRAINT dr_drills_environment_not_empty
        CHECK (length(trim(environment)) > 0),

    CONSTRAINT dr_drills_trigger_not_empty
        CHECK (length(trim(trigger)) > 0),

    CONSTRAINT dr_drills_actor_not_empty
        CHECK (length(trim(actor)) > 0),

    CONSTRAINT dr_drills_status_valid
        CHECK (
            status IN (
                'RUNNING',
                'SUCCEEDED',
                'FAILED',
                'CANCELLED'
            )
        ),

    CONSTRAINT dr_drills_readiness_score_valid
        CHECK (
            readiness_score IS NULL
            OR (readiness_score >= 0 AND readiness_score <= 100)
        )
);

CREATE INDEX IF NOT EXISTS dr_drills_plan_idx
    ON disaster_recovery.dr_drills (plan_id);

CREATE INDEX IF NOT EXISTS dr_drills_status_idx
    ON disaster_recovery.dr_drills (status);

CREATE INDEX IF NOT EXISTS dr_drills_started_at_idx
    ON disaster_recovery.dr_drills (started_at DESC);

CREATE TABLE IF NOT EXISTS disaster_recovery.dr_drill_steps (
    step_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drill_id       UUID NOT NULL
        REFERENCES disaster_recovery.dr_drills(drill_id)
        ON DELETE CASCADE,
    step_name      TEXT NOT NULL,
    step_order     INTEGER NOT NULL,
    status         TEXT NOT NULL DEFAULT 'PENDING',
    started_at     TIMESTAMPTZ,
    completed_at   TIMESTAMPTZ,
    result         JSONB NOT NULL DEFAULT '{}'::jsonb,
    error          TEXT,

    CONSTRAINT dr_drill_steps_step_name_not_empty
        CHECK (length(trim(step_name)) > 0),

    CONSTRAINT dr_drill_steps_status_valid
        CHECK (
            status IN (
                'PENDING',
                'RUNNING',
                'SUCCEEDED',
                'FAILED',
                'SKIPPED'
            )
        ),

    CONSTRAINT dr_drill_steps_drill_step_order_unique
        UNIQUE (drill_id, step_order)
);

CREATE INDEX IF NOT EXISTS dr_drill_steps_drill_idx
    ON disaster_recovery.dr_drill_steps (drill_id);

CREATE TABLE IF NOT EXISTS disaster_recovery.dr_events (
    event_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id      UUID REFERENCES disaster_recovery.recovery_plans(plan_id) ON DELETE SET NULL,
    drill_id     UUID REFERENCES disaster_recovery.dr_drills(drill_id) ON DELETE SET NULL,
    event_type   TEXT NOT NULL,
    severity     TEXT NOT NULL DEFAULT 'INFO',
    actor        TEXT NOT NULL DEFAULT 'system',
    reason       TEXT NOT NULL DEFAULT '',
    details      JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT dr_events_event_type_not_empty
        CHECK (length(trim(event_type)) > 0),

    CONSTRAINT dr_events_actor_not_empty
        CHECK (length(trim(actor)) > 0),

    CONSTRAINT dr_events_severity_valid
        CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL'))
);

CREATE INDEX IF NOT EXISTS dr_events_plan_idx
    ON disaster_recovery.dr_events (plan_id);

CREATE INDEX IF NOT EXISTS dr_events_drill_idx
    ON disaster_recovery.dr_events (drill_id);

CREATE INDEX IF NOT EXISTS dr_events_occurred_at_idx
    ON disaster_recovery.dr_events (occurred_at DESC);

DROP TRIGGER IF EXISTS dr_events_no_update
    ON disaster_recovery.dr_events;

CREATE TRIGGER dr_events_no_update
BEFORE UPDATE ON disaster_recovery.dr_events
FOR EACH ROW
EXECUTE FUNCTION disaster_recovery.prevent_event_mutation();

DROP TRIGGER IF EXISTS dr_events_no_delete
    ON disaster_recovery.dr_events;

CREATE TRIGGER dr_events_no_delete
BEFORE DELETE ON disaster_recovery.dr_events
FOR EACH ROW
EXECUTE FUNCTION disaster_recovery.prevent_event_mutation();

COMMIT;