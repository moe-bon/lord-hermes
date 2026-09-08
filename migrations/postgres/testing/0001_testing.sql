-- ApexQuant Ultra
-- PostgreSQL test-run registry, result storage, and failure-mode catalog.

BEGIN;

CREATE SCHEMA IF NOT EXISTS testing;

DO $$
BEGIN
    CREATE TYPE testing.test_status AS ENUM (
        'PASSED',
        'FAILED',
        'SKIPPED',
        'ERROR'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE TABLE IF NOT EXISTS testing.test_runs (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment     TEXT NOT NULL,
    git_sha         TEXT,
    trigger         TEXT NOT NULL DEFAULT 'manual',
    started_at      TIMESTAMPTZ NOT NULL,
    completed_at    TIMESTAMPTZ NOT NULL,
    ok              BOOLEAN NOT NULL,
    total           INTEGER NOT NULL DEFAULT 0,
    passed          INTEGER NOT NULL DEFAULT 0,
    failed          INTEGER NOT NULL DEFAULT 0,
    skipped         INTEGER NOT NULL DEFAULT 0,
    errors          INTEGER NOT NULL DEFAULT 0,
    coverage_pct    NUMERIC(5,2),
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT test_runs_environment_not_empty
        CHECK (length(trim(environment)) > 0),

    CONSTRAINT test_runs_trigger_not_empty
        CHECK (length(trim(trigger)) > 0),

    CONSTRAINT test_runs_total_nonnegative
        CHECK (total >= 0),

    CONSTRAINT test_runs_passed_nonnegative
        CHECK (passed >= 0),

    CONSTRAINT test_runs_failed_nonnegative
        CHECK (failed >= 0),

    CONSTRAINT test_runs_skipped_nonnegative
        CHECK (skipped >= 0),

    CONSTRAINT test_runs_errors_nonnegative
        CHECK (errors >= 0),

    CONSTRAINT test_runs_completed_after_started
        CHECK (completed_at >= started_at)
);

CREATE INDEX IF NOT EXISTS testing_test_runs_started_at_idx
    ON testing.test_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS testing_test_runs_ok_idx
    ON testing.test_runs (ok);

CREATE INDEX IF NOT EXISTS testing_test_runs_environment_idx
    ON testing.test_runs (environment);

CREATE TABLE IF NOT EXISTS testing.test_results (
    result_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL
        REFERENCES testing.test_runs(run_id)
        ON DELETE CASCADE,
    suite           TEXT NOT NULL,
    name            TEXT NOT NULL,
    status          testing.test_status NOT NULL,
    duration_ms     DOUBLE PRECISION NOT NULL DEFAULT 0,
    message         TEXT,
    details         JSONB NOT NULL DEFAULT '{}'::jsonb,
    failure_mode    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT test_results_suite_not_empty
        CHECK (length(trim(suite)) > 0),

    CONSTRAINT test_results_name_not_empty
        CHECK (length(trim(name)) > 0),

    CONSTRAINT test_results_duration_nonnegative
        CHECK (duration_ms >= 0)
);

CREATE INDEX IF NOT EXISTS testing_test_results_run_id_idx
    ON testing.test_results (run_id);

CREATE INDEX IF NOT EXISTS testing_test_results_suite_idx
    ON testing.test_results (suite);

CREATE INDEX IF NOT EXISTS testing_test_results_status_idx
    ON testing.test_results (status);

CREATE INDEX IF NOT EXISTS testing_test_results_failure_mode_idx
    ON testing.test_results (failure_mode);

CREATE TABLE IF NOT EXISTS testing.failure_mode_catalog (
    failure_mode    TEXT PRIMARY KEY,
    category        TEXT NOT NULL,
    description     TEXT NOT NULL,
    severity        TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT failure_mode_catalog_category_not_empty
        CHECK (length(trim(category)) > 0),

    CONSTRAINT failure_mode_catalog_description_not_empty
        CHECK (length(trim(description)) > 0),

    CONSTRAINT failure_mode_catalog_severity_valid
        CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL'))
);

INSERT INTO testing.failure_mode_catalog (
    failure_mode,
    category,
    description,
    severity
)
VALUES
    ('network_partition', 'network', 'Network connectivity between services is lost.', 'CRITICAL'),
    ('dependency_timeout', 'timeout', 'A required dependency does not respond within the allowed budget.', 'CRITICAL'),
    ('duplicate_event', 'idempotency', 'The same event or command is delivered more than once.', 'CRITICAL'),
    ('corrupted_payload', 'data_integrity', 'Payload fails schema, checksum, or semantic validation.', 'CRITICAL'),
    ('missing_field', 'data_integrity', 'A required field is absent from an event or command.', 'CRITICAL'),
    ('stale_state', 'consistency', 'State is older than the allowed freshness window.', 'CRITICAL'),
    ('restart_mid_operation', 'recovery', 'Service restarts while an operation is in flight.', 'CRITICAL'),
    ('clock_skew', 'time', 'System clocks diverge beyond tolerance.', 'WARNING'),
    ('nan_or_infinite_input', 'input_validation', 'Numeric input is NaN or infinite.', 'CRITICAL'),
    ('unauthorized_access', 'security', 'Caller lacks required authentication or authorization.', 'CRITICAL'),
    ('rate_limit_exceeded', 'capacity', 'Caller exceeds allowed request or event rate.', 'WARNING'),
    ('broker_disconnection', 'external_dependency', 'Broker or exchange connection is lost.', 'CRITICAL'),
    ('database_unavailable', 'external_dependency', 'Primary transactional database is unavailable.', 'CRITICAL'),
    ('event_bus_unavailable', 'external_dependency', 'Kafka/Redpanda event backbone is unavailable.', 'CRITICAL'),
    ('secret_unavailable', 'security', 'Required secret or key material is unavailable.', 'CRITICAL')
ON CONFLICT (failure_mode) DO NOTHING;

COMMIT;