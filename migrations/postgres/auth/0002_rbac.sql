-- ApexQuant Ultra — Feature 0.12 (Definitive): RBAC storage-time layer.

BEGIN;

-- 0. Typed service identity: planes
DO $$
BEGIN
    CREATE TYPE auth.plane_type AS ENUM (
        'CONTROL','MARKET_DATA','TRADING','RISK','AI','DATA_RESEARCH','OBSERVABILITY'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE auth.principals
    ADD COLUMN IF NOT EXISTS plane auth.plane_type NOT NULL DEFAULT 'CONTROL';

CREATE INDEX IF NOT EXISTS auth_principals_plane_idx ON auth.principals (plane);

-- ===========================================================================
-- 1. Permission grammar guard (structural defense-in-depth; the authoritative
--    grammar lives in data/rbac/forbidden_matrix.yaml and is enforced at
--    grant-time by the app).
-- ===========================================================================
CREATE OR REPLACE FUNCTION auth.is_valid_permission(p TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    segs TEXT[];
    seg  TEXT;
BEGIN
    IF p IS NULL OR p = '' THEN RETURN FALSE; END IF;
    IF p = '*' THEN RETURN TRUE; END IF;
    IF p <> lower(p) THEN RETURN FALSE; END IF;
    segs := string_to_array(p, ':');
    IF array_length(segs,1) < 2 OR array_length(segs,1) > 3 THEN RETURN FALSE; END IF;
    FOREACH seg IN ARRAY segs LOOP
        IF seg = '*' THEN CONTINUE; END IF;
        IF seg !~ '^[a-z0-9_-]+$' THEN RETURN FALSE; END IF;
    END LOOP;
    RETURN TRUE;
END; $$;

-- ===========================================================================
-- 2. Roles, role permissions, principal roles
-- ===========================================================================
CREATE TABLE IF NOT EXISTS auth.roles (
    role_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_name      TEXT NOT NULL UNIQUE,
    description    TEXT NOT NULL DEFAULT '',
    system_managed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT roles_role_name_not_empty CHECK (length(trim(role_name)) > 0)
);

CREATE TABLE IF NOT EXISTS auth.role_permissions (
    role_id    UUID NOT NULL REFERENCES auth.roles(role_id) ON DELETE CASCADE,
    permission TEXT NOT NULL,
    PRIMARY KEY (role_id, permission),
    CONSTRAINT role_permissions_grammar CHECK (auth.is_valid_permission(permission))
);

CREATE TABLE IF NOT EXISTS auth.principal_roles (
    principal_id UUID NOT NULL REFERENCES auth.principals(principal_id) ON DELETE CASCADE,
    role_id      UUID NOT NULL REFERENCES auth.roles(role_id)        ON DELETE CASCADE,
    granted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    granted_by   TEXT,
    PRIMARY KEY (principal_id, role_id)
);

CREATE TABLE IF NOT EXISTS auth.role_plane_bindings (
    role_id UUID NOT NULL REFERENCES auth.roles(role_id) ON DELETE CASCADE,
    plane   auth.plane_type NOT NULL,
    PRIMARY KEY (role_id, plane)
);

CREATE TABLE IF NOT EXISTS auth.role_mutual_exclusions (
    role_a UUID NOT NULL REFERENCES auth.roles(role_id) ON DELETE CASCADE,
    role_b UUID NOT NULL REFERENCES auth.roles(role_id) ON DELETE CASCADE,
    PRIMARY KEY (role_a, role_b),
    CONSTRAINT role_mutual_exclusions_distinct CHECK (role_a <> role_b)
);

CREATE UNIQUE INDEX IF NOT EXISTS role_mutual_exclusions_canonical_idx
    ON auth.role_mutual_exclusions (LEAST(role_a, role_b), GREATEST(role_a, role_b));

-- ===========================================================================
-- 3. Emergency-stop carve-out (Engineering Contract #15).
--    emergency_stop is NOT an RBAC permission and cannot be granted via RBAC.
--    The emergency global stop is authorized out-of-band (mTLS / console).
-- ===========================================================================
CREATE TABLE IF NOT EXISTS auth.emergency_stop_channels (
    channel_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    identity     TEXT NOT NULL UNIQUE,          -- mTLS cert fingerprint / console id
    channel_type TEXT NOT NULL,                 -- 'MTLS' | 'CONSOLE'
    active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION auth.enforce_emergency_stop_carveout()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.permission = 'emergency_stop' OR NEW.permission LIKE 'emergency_stop:%' THEN
        RAISE EXCEPTION
            'emergency_stop is out-of-band of RBAC (Engineering Contract #15); '
            'it cannot be granted via RBAC';
    END IF;
    RETURN NEW;
END; $$;

DROP TRIGGER IF EXISTS trg_emergency_stop_grants ON auth.permission_grants;
CREATE TRIGGER trg_emergency_stop_grants
BEFORE INSERT ON auth.permission_grants
FOR EACH ROW EXECUTE FUNCTION auth.enforce_emergency_stop_carveout();

DROP TRIGGER IF EXISTS trg_emergency_stop_role_perms ON auth.role_permissions;
CREATE TRIGGER trg_emergency_stop_role_perms
BEFORE INSERT ON auth.role_permissions
FOR EACH ROW EXECUTE FUNCTION auth.enforce_emergency_stop_carveout();

-- ===========================================================================
-- 4. Plane immutability (eliminates plane-transition attacks)
-- ===========================================================================
CREATE OR REPLACE FUNCTION auth.enforce_plane_immutable()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.plane IS DISTINCT FROM OLD.plane THEN
        RAISE EXCEPTION
            'principal plane is immutable; provision a new principal and archive the old one';
    END IF;
    RETURN NEW;
END; $$;

DROP TRIGGER IF EXISTS trg_plane_immutable ON auth.principals;
CREATE TRIGGER trg_plane_immutable
BEFORE UPDATE ON auth.principals
FOR EACH ROW EXECUTE FUNCTION auth.enforce_plane_immutable();

-- ===========================================================================
-- 5. Mutual exclusion (storage-time)
-- ===========================================================================
CREATE OR REPLACE FUNCTION auth.enforce_mutual_exclusion()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM auth.principal_roles pr
        JOIN auth.role_mutual_exclusions me
          ON (me.role_a = pr.role_id AND me.role_b = NEW.role_id)
          OR (me.role_b = pr.role_id AND me.role_a = NEW.role_id)
        WHERE pr.principal_id = NEW.principal_id
    ) THEN
        RAISE EXCEPTION 'mutual-exclusion violation for principal %', NEW.principal_id;
    END IF;
    RETURN NEW;
END; $$;

DROP TRIGGER IF EXISTS trg_mutual_exclusion ON auth.principal_roles;
CREATE TRIGGER trg_mutual_exclusion
BEFORE INSERT OR UPDATE ON auth.principal_roles
FOR EACH ROW EXECUTE FUNCTION auth.enforce_mutual_exclusion();

-- ===========================================================================
-- 6. Plane-role binding (storage-time)
-- ===========================================================================
CREATE OR REPLACE FUNCTION auth.enforce_plane_role_binding()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_plane auth.plane_type;
BEGIN
    SELECT plane INTO v_plane FROM auth.principals WHERE principal_id = NEW.principal_id;
    IF v_plane IS NULL THEN
        RAISE EXCEPTION 'principal % not found', NEW.principal_id;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM auth.role_plane_bindings
        WHERE role_id = NEW.role_id AND plane = v_plane
    ) THEN
        RAISE EXCEPTION 'role % is not assignable to plane %', NEW.role_id, v_plane;
    END IF;
    RETURN NEW;
END; $$;

DROP TRIGGER IF EXISTS trg_plane_role_binding ON auth.principal_roles;
CREATE TRIGGER trg_plane_role_binding
BEFORE INSERT OR UPDATE ON auth.principal_roles
FOR EACH ROW EXECUTE FUNCTION auth.enforce_plane_role_binding();

-- ===========================================================================
-- 7. Direct-grant grammar guard
-- ===========================================================================
ALTER TABLE auth.permission_grants
    ADD CONSTRAINT permission_grants_grammar
    CHECK (auth.is_valid_permission(permission));

-- ===========================================================================
-- 8. Immutable RBAC lifecycle audit (grants/revocations/lifecycle -> 0.13 trail)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS auth.rbac_audit (
    audit_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor        TEXT NOT NULL,
    action       TEXT NOT NULL,      -- GRANT | REVOKE | ROLE_CREATED | ROLE_DELETED | MACHINE_REMEDIATION
    principal_id UUID,
    role_id      UUID,
    permission   TEXT,
    detail       JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE OR REPLACE FUNCTION auth.prevent_audit_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'rbac_audit is append-only';
END; $$;

DROP TRIGGER IF EXISTS trg_rbac_audit_immutable ON auth.rbac_audit;
CREATE TRIGGER trg_rbac_audit_immutable
BEFORE UPDATE OR DELETE ON auth.rbac_audit
FOR EACH ROW EXECUTE FUNCTION auth.prevent_audit_mutation();

-- ===========================================================================
-- 9. Dedicated security-deny stream (separate retention; flood-isolated)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS auth.rbac_denials (
    denial_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    principal_id UUID,
    subject_name TEXT,
    permission   TEXT NOT NULL,
    reason       TEXT NOT NULL,
    request_id   TEXT
);

CREATE INDEX IF NOT EXISTS auth_rbac_denials_occurred_at_idx
    ON auth.rbac_denials (occurred_at DESC);

CREATE INDEX IF NOT EXISTS auth_rbac_denials_subject_idx
    ON auth.rbac_denials (subject_name, occurred_at DESC);

-- ===========================================================================
-- 10. Reconciliation runs, violations, remediations, alerts
-- ===========================================================================
CREATE TABLE IF NOT EXISTS auth.rbac_reconciliation_runs (
    run_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at  TIMESTAMPTZ,
    trigger       TEXT NOT NULL DEFAULT 'SCHEDULED',   -- SCHEDULED | ON_DEMAND
    violations    INTEGER NOT NULL DEFAULT 0,
    remediations  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS auth.rbac_violations (
    violation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id       UUID NOT NULL REFERENCES auth.rbac_reconciliation_runs(run_id) ON DELETE CASCADE,
    principal_id UUID,
    category     TEXT NOT NULL,   -- FORBIDDEN_PERMISSION | MUTUAL_EXCLUSION | PLANE_BINDING | UNPROVISIONED
    detail       TEXT NOT NULL,
    detected_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS auth.rbac_remediations (
    remediation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id         UUID NOT NULL REFERENCES auth.rbac_reconciliation_runs(run_id) ON DELETE CASCADE,
    violation_id   UUID NOT NULL REFERENCES auth.rbac_violations(violation_id) ON DELETE CASCADE,
    action         TEXT NOT NULL,    -- AUTO_REVOKE_ROLE | AUTO_REVOKE_GRANT
    detail         TEXT NOT NULL,
    remediated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS auth.rbac_alerts (
    alert_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raised_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    severity    TEXT NOT NULL,       -- CRITICAL | WARNING
    category    TEXT NOT NULL,       -- INVARIANT_VIOLATION | DENIAL_RATE_ANOMALY | RECONCILIATION
    detail      TEXT NOT NULL
);

-- ===========================================================================
-- 11. Seed canonical roles, bindings, exclusions
-- ===========================================================================
INSERT INTO auth.roles (role_name, description, system_managed) VALUES
    ('SUPER_ADMIN',       'Unrestricted governance. Control plane only. Never AI.', TRUE),
    ('SYSTEM_ADMIN',      'System configuration and administration.',                TRUE),
    ('RISK_ADMIN',        'Routine risk limits, circuit breakers, routine kill switch.', TRUE),
    ('STRATEGY_ADMIN',    'Strategy registry and lifecycle.',                        TRUE),
    ('MODEL_ADMIN',       'Model registry, datasets, experiments.',                  TRUE),
    ('TRADER',            'Read access to orders/positions/execution.',             TRUE),
    ('VIEWER',            'Read-only telemetry and state.',                         TRUE),
    ('AI_SERVICE',        'AI/research service identity. Cannot execute.',          TRUE),
    ('EXECUTION_SERVICE', 'Execution service identity. Authorized to execute.',     TRUE)
ON CONFLICT (role_name) DO NOTHING;

WITH r(role_id, role_name) AS (SELECT role_id, role_name FROM auth.roles)
INSERT INTO auth.role_permissions (role_id, permission)
SELECT role_id, perm FROM r, unnest(ARRAY['*']) AS perm
WHERE role_name='SUPER_ADMIN' ON CONFLICT DO NOTHING;

WITH r(role_id, role_name) AS (SELECT role_id, role_name FROM auth.roles)
INSERT INTO auth.role_permissions (role_id, permission)
SELECT role_id, perm FROM r, unnest(ARRAY['system:*','auth:*','config:*','audit:read']) AS perm
WHERE role_name='SYSTEM_ADMIN' ON CONFLICT DO NOTHING;

WITH r(role_id, role_name) AS (SELECT role_id, role_name FROM auth.roles)
INSERT INTO auth.role_permissions (role_id, permission)
SELECT role_id, perm FROM r, unnest(ARRAY['risk:*','kill_switch:routine','circuit_breaker:*','trading:freeze']) AS perm
WHERE role_name='RISK_ADMIN' ON CONFLICT DO NOTHING;

WITH r(role_id, role_name) AS (SELECT role_id, role_name FROM auth.roles)
INSERT INTO auth.role_permissions (role_id, permission)
SELECT role_id, perm FROM r, unnest(ARRAY['strategy:*','portfolio:*','backtest:*']) AS perm
WHERE role_name='STRATEGY_ADMIN' ON CONFLICT DO NOTHING;

WITH r(role_id, role_name) AS (SELECT role_id, role_name FROM auth.roles)
INSERT INTO auth.role_permissions (role_id, permission)
SELECT role_id, perm FROM r, unnest(ARRAY['model:*','dataset:*','experiment:*','feature:*']) AS perm
WHERE role_name='MODEL_ADMIN' ON CONFLICT DO NOTHING;

WITH r(role_id, role_name) AS (SELECT role_id, role_name FROM auth.roles)
INSERT INTO auth.role_permissions (role_id, permission)
SELECT role_id, perm FROM r, unnest(ARRAY['execution:read','position:read','strategy:read','market_data:read']) AS perm
WHERE role_name='TRADER' ON CONFLICT DO NOTHING;

WITH r(role_id, role_name) AS (SELECT role_id, role_name FROM auth.roles)
INSERT INTO auth.role_permissions (role_id, permission)
SELECT role_id, perm FROM r, unnest(ARRAY['*:read']) AS perm
WHERE role_name='VIEWER' ON CONFLICT DO NOTHING;

WITH r(role_id, role_name) AS (SELECT role_id, role_name FROM auth.roles)
INSERT INTO auth.role_permissions (role_id, permission)
SELECT role_id, perm FROM r, unnest(ARRAY['model:read','feature:read','market_data:read','knowledge:read','prediction:write']) AS perm
WHERE role_name='AI_SERVICE' ON CONFLICT DO NOTHING;

WITH r(role_id, role_name) AS (SELECT role_id, role_name FROM auth.roles)
INSERT INTO auth.role_permissions (role_id, permission)
SELECT role_id, perm FROM r, unnest(ARRAY['execution:submit','execution:write','execution:read','broker:read','position:read','market_data:read']) AS perm
WHERE role_name='EXECUTION_SERVICE' ON CONFLICT DO NOTHING;

-- Plane-role bindings (typed service roles)
INSERT INTO auth.role_plane_bindings (role_id, plane)
SELECT r.role_id, b.plane::auth.plane_type
FROM auth.roles r
JOIN (VALUES
    ('SUPER_ADMIN','CONTROL'),
    ('SYSTEM_ADMIN','CONTROL'),
    ('RISK_ADMIN','CONTROL'), ('RISK_ADMIN','RISK'),
    ('STRATEGY_ADMIN','CONTROL'), ('STRATEGY_ADMIN','TRADING'),
    ('MODEL_ADMIN','CONTROL'), ('MODEL_ADMIN','AI'),
    ('TRADER','TRADING'), ('TRADER','CONTROL'),
    ('VIEWER','CONTROL'), ('VIEWER','MARKET_DATA'), ('VIEWER','TRADING'),
    ('VIEWER','RISK'), ('VIEWER','OBSERVABILITY'),
    ('AI_SERVICE','AI'), ('AI_SERVICE','DATA_RESEARCH'),
    ('EXECUTION_SERVICE','RISK'), ('EXECUTION_SERVICE','TRADING')
) AS b(role_name, plane) ON b.role_name = r.role_name
ON CONFLICT DO NOTHING;

-- Explicit mutual exclusion: AI_SERVICE <-> EXECUTION_SERVICE
INSERT INTO auth.role_mutual_exclusions (role_a, role_b)
SELECT a.role_id, b.role_id
FROM auth.roles a, auth.roles b
WHERE a.role_name='AI_SERVICE' AND b.role_name='EXECUTION_SERVICE'
ON CONFLICT DO NOTHING;

COMMIT;