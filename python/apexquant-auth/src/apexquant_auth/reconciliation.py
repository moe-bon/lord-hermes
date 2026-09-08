from __future__ import annotations

import json
from dataclasses import dataclass, field

from apexquant_auth.rbac import forbidden_patterns, is_restricted, overlaps


SWEEP_INTERVAL_SECONDS = 30          # spec-mandated cadence (testable)
DENIAL_RATE_LIMIT_PER_SEC = 50       # anomaly threshold -> alert (attack signature)


@dataclass
class Violation:
    principal_id: str
    category: str
    detail: str


@dataclass
class ReconciliationResult:
    violations: list[Violation] = field(default_factory=list)
    remediations: list[str] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)


def _effective_assignments(rows: list[dict]) -> dict[str, dict]:
    """Group role-permissions and direct-grants by principal."""
    out: dict[str, dict] = {}
    for row in rows:
        pid = row["principal_id"]
        entry = out.setdefault(pid, {
            "plane": row["plane"],
            "subject": row["subject_name"],
            "role_permissions": [],
            "direct_grants": [],
            "role_count": row.get("role_count", 0),
            "assignments": [],
        })
        if row.get("role_permission"):
            entry["role_permissions"].append(row["role_permission"])
            entry["assignments"].append(("ROLE", row.get("role_id"), row["role_permission"]))
        if row.get("direct_grant"):
            entry["direct_grants"].append(row["direct_grant"])
            entry["assignments"].append(("DIRECT", None, row["direct_grant"]))
    return out


def detect_violations(assignments: dict[str, dict]) -> list[Violation]:
    violations: list[Violation] = []
    for pid, entry in assignments.items():
        plane = entry["plane"]
        effective = entry["role_permissions"] + entry["direct_grants"]

        # FORBIDDEN_PERMISSION (invariant drift / compromise detection)
        if is_restricted(plane):
            for perm in effective:
                if perm == "*":
                    violations.append(Violation(pid, "FORBIDDEN_PERMISSION",
                        f"plane={plane} subject={entry['subject']} permission=*"))
                    continue
                for d in forbidden_patterns(plane):
                    if overlaps(perm, d):
                        violations.append(Violation(pid, "FORBIDDEN_PERMISSION",
                            f"plane={plane} subject={entry['subject']} permission={perm}"))

        # UNPROVISIONED (direct grants but no roles)
        if entry["role_count"] == 0 and entry["direct_grants"]:
            violations.append(Violation(pid, "UNPROVISIONED",
                f"subject={entry['subject']} has {len(entry['direct_grants'])} direct grants but no roles"))

    return violations


def reconcile_and_remediate(conn, trigger: str = "SCHEDULED") -> ReconciliationResult:
    """Runs every 30s (scheduled) or on demand. Detects, auto-revokes, alerts."""
    result = ReconciliationResult()

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO auth.rbac_reconciliation_runs (trigger)
            VALUES (%s) RETURNING run_id
            """,
            (trigger,),
        )
        run_id = cur.fetchone()[0]

        cur.execute(
            """
            SELECT p.principal_id, p.plane, p.subject_name,
                   COUNT(DISTINCT pr.role_id) AS role_count
            FROM auth.principals p
            LEFT JOIN auth.principal_roles pr ON pr.principal_id = p.principal_id
            GROUP BY p.principal_id, p.plane, p.subject_name
            """
        )
        principals = {r[0]: {"plane": r[1], "subject": r[2], "role_count": r[3]} for r in cur.fetchall()}

        cur.execute(
            """
            SELECT pr.principal_id, rp.permission AS role_permission, pr.role_id
            FROM auth.principal_roles pr
            JOIN auth.role_permissions rp ON rp.role_id = pr.role_id
            """
        )
        role_rows = cur.fetchall()

        cur.execute(
            """
            SELECT principal_id, permission AS direct_grant
            FROM auth.permission_grants
            """
        )
        grant_rows = cur.fetchall()

    assignments: dict[str, dict] = {}
    for pid, meta in principals.items():
        assignments[pid] = {
            "plane": meta["plane"], "subject": meta["subject"],
            "role_permissions": [], "direct_grants": [],
            "role_count": meta["role_count"], "assignments": [],
        }
    for pid, perm, role_id in role_rows:
        if pid in assignments:
            assignments[pid]["role_permissions"].append(perm)
            assignments[pid]["assignments"].append(("ROLE", role_id, perm))
    for pid, perm in grant_rows:
        if pid in assignments:
            assignments[pid]["direct_grants"].append(perm)
            assignments[pid]["assignments"].append(("DIRECT", None, perm))

    violations = detect_violations(assignments)
    result.violations = violations

    with conn.cursor() as cur:
        for v in violations:
            cur.execute(
                "INSERT INTO auth.rbac_violations (run_id, principal_id, category, detail) "
                "VALUES (%s, %s, %s, %s) RETURNING violation_id",
                (run_id, v.principal_id, v.category, v.detail),
            )
            violation_id = cur.fetchone()[0]

            # AUTO-REMEDIATE: quarantine the offending assignments.
            entry = assignments[v.principal_id]
            if v.category == "FORBIDDEN_PERMISSION":
                for kind, role_id, perm in entry["assignments"]:
                    from apexquant_auth.rbac import overlaps as _ov, forbidden_patterns as _fp
                    bad = perm == "*" or any(_ov(perm, d) for d in _fp(entry["plane"]))
                    if not bad:
                        continue
                    if kind == "ROLE":
                        cur.execute(
                            "DELETE FROM auth.principal_roles WHERE principal_id=%s AND role_id=%s",
                            (v.principal_id, role_id),
                        )
                        action = "AUTO_REVOKE_ROLE"
                    else:
                        cur.execute(
                            "DELETE FROM auth.permission_grants WHERE principal_id=%s AND permission=%s",
                            (v.principal_id, perm),
                        )
                        action = "AUTO_REVOKE_GRANT"
                    cur.execute(
                        "INSERT INTO auth.rbac_remediations (run_id, violation_id, action, detail) "
                        "VALUES (%s, %s, %s, %s)",
                        (run_id, violation_id, action, f"permission={perm}"),
                    )
                    cur.execute(
                        "INSERT INTO auth.rbac_audit (actor, action, principal_id, permission, detail) "
                        "VALUES ('reconciliation-sweep', 'MACHINE_REMEDIATION', %s, %s, %s)",
                        (v.principal_id, perm, json.dumps({"run_id": str(run_id)})),
                    )
                    result.remediations.append(f"{action}:{perm}")

            elif v.category == "UNPROVISIONED":
                cur.execute(
                    "DELETE FROM auth.permission_grants WHERE principal_id=%s",
                    (v.principal_id,),
                )
                cur.execute(
                    "INSERT INTO auth.rbac_remediations (run_id, violation_id, action, detail) "
                    "VALUES (%s, %s, %s, %s)",
                    (run_id, violation_id, "AUTO_REVOKE_GRANT", "unprovisioned direct grants"),
                )
                result.remediations.append("AUTO_REVOKE_GRANT:unprovisioned")

        if violations:
            cur.execute(
                "INSERT INTO auth.rbac_alerts (severity, category, detail) VALUES ('CRITICAL', 'INVARIANT_VIOLATION', %s)",
                (f"{len(violations)} RBAC invariant violation(s) detected and remediated",),
            )
            result.alerts.append("CRITICAL:INVARIANT_VIOLATION")

        cur.execute(
            "UPDATE auth.rbac_reconciliation_runs SET completed_at=now(), violations=%s, remediations=%s WHERE run_id=%s",
            (len(violations), len(result.remediations), run_id),
        )

    conn.commit()
    return result


def log_denial(conn, principal_id, subject_name, permission, reason, request_id=None) -> bool:
    """Write to the dedicated deny stream; return True if a denial-rate anomaly is detected."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO auth.rbac_denials (principal_id, subject_name, permission, reason, request_id) "
            "VALUES (%s, %s, %s, %s, %s)",
            (principal_id, subject_name, permission, reason, request_id),
        )
        cur.execute(
            "SELECT COUNT(*) FROM auth.rbac_denials "
            "WHERE subject_name=%s AND occurred_at > now() - interval '1 second'",
            (subject_name,),
        )
        rate = cur.fetchone()[0]
        anomaly = rate > DENIAL_RATE_LIMIT_PER_SEC
        if anomaly:
            cur.execute(
                "INSERT INTO auth.rbac_alerts (severity, category, detail) VALUES ('CRITICAL', 'DENIAL_RATE_ANOMALY', %s)",
                (f"subject={subject_name} denial_rate={rate}/s",),
            )
    conn.commit()
    return anomaly