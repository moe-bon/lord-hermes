from apexquant_disaster_recovery.models import (
    BackupRequirementStatus,
    HealthCheckStatus,
)
from apexquant_disaster_recovery.scoring import score_readiness


def fresh_verified_requirement() -> BackupRequirementStatus:
    return BackupRequirementStatus(
        component_name="postgresql-primary",
        backup_policy_name="local-postgres",
        required=True,
        policy_exists=True,
        fresh=True,
        verified=True,
        rpo_seconds=3600,
    )


def test_ready_when_all_requirements_pass() -> None:
    score, state, fail_closed = score_readiness(
        plan_active=True,
        backup_requirements=[fresh_verified_requirement()],
        health_checks=[],
        recent_drill_passed=True,
    )

    assert score == 100.0
    assert state == "READY"
    assert fail_closed is False


def test_fail_closed_when_backup_stale() -> None:
    stale = fresh_verified_requirement()
    stale.fresh = False

    score, state, fail_closed = score_readiness(
        plan_active=True,
        backup_requirements=[stale],
        health_checks=[],
        recent_drill_passed=True,
    )

    assert fail_closed is True
    assert score <= 49.0
    assert state == "NOT_READY"


def test_inactive_plan_is_not_ready() -> None:
    score, state, fail_closed = score_readiness(
        plan_active=False,
        backup_requirements=[fresh_verified_requirement()],
        health_checks=[],
        recent_drill_passed=True,
    )

    assert score == 0.0
    assert state == "NOT_READY"
    assert fail_closed is True


def test_failed_health_check_caps_score() -> None:
    health = HealthCheckStatus(
        component_name="backup-recovery-core",
        health_endpoint="http://backup-recovery-core:8093/healthz",
        applicable=True,
        checked=True,
        healthy=False,
    )

    score, state, fail_closed = score_readiness(
        plan_active=True,
        backup_requirements=[fresh_verified_requirement()],
        health_checks=[health],
        recent_drill_passed=True,
    )

    assert score <= 79.0
    assert state in {"DEGRADED", "NOT_READY"}