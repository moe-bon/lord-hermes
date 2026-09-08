from __future__ import annotations

from apexquant_disaster_recovery.models import (
    BackupRequirementStatus,
    HealthCheckStatus,
)

WEIGHT_PLAN_ACTIVE = 10.0
WEIGHT_BACKUP_FRESHNESS = 40.0
WEIGHT_BACKUP_VERIFICATION = 25.0
WEIGHT_HEALTH = 15.0
WEIGHT_RECENT_DRILL = 10.0

READY_THRESHOLD = 90.0
DEGRADED_THRESHOLD = 70.0
BACKUP_FAIL_CLOSED_CAP = 49.0
HEALTH_FAILURE_CAP = 79.0


def score_readiness(
    plan_active: bool,
    backup_requirements: list[BackupRequirementStatus],
    health_checks: list[HealthCheckStatus],
    recent_drill_passed: bool,
) -> tuple[float, str, bool]:
    score = 0.0
    fail_closed_triggered = False

    if not plan_active:
        return 0.0, "NOT_READY", True

    score += WEIGHT_PLAN_ACTIVE

    required_backups = [
        requirement
        for requirement in backup_requirements
        if requirement.required
    ]

    if required_backups:
        fresh_count = sum(1 for requirement in required_backups if requirement.fresh)
        verified_count = sum(1 for requirement in required_backups if requirement.verified)

        freshness_ratio = fresh_count / len(required_backups)
        verification_ratio = verified_count / len(required_backups)

        score += WEIGHT_BACKUP_FRESHNESS * freshness_ratio
        score += WEIGHT_BACKUP_VERIFICATION * verification_ratio

        if fresh_count < len(required_backups):
            fail_closed_triggered = True
    else:
        score += WEIGHT_BACKUP_FRESHNESS
        score += WEIGHT_BACKUP_VERIFICATION

    applicable_health_checks = [
        health_check
        for health_check in health_checks
        if health_check.applicable
    ]

    if applicable_health_checks:
        healthy_count = sum(
            1
            for health_check in applicable_health_checks
            if health_check.healthy is True
        )

        health_ratio = healthy_count / len(applicable_health_checks)

        score += WEIGHT_HEALTH * health_ratio

        if healthy_count < len(applicable_health_checks):
            score = min(score, HEALTH_FAILURE_CAP)
    else:
        score += WEIGHT_HEALTH

    if recent_drill_passed:
        score += WEIGHT_RECENT_DRILL

    if fail_closed_triggered:
        score = min(score, BACKUP_FAIL_CLOSED_CAP)

    score = max(0.0, min(100.0, score))

    if score >= READY_THRESHOLD:
        state = "READY"
    elif score >= DEGRADED_THRESHOLD:
        state = "DEGRADED"
    else:
        state = "NOT_READY"

    return score, state, fail_closed_triggered