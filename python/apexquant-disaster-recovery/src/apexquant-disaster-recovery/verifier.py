from __future__ import annotations

from datetime import timedelta

from apexquant_disaster_recovery.backup_provider import BackupStatusProvider
from apexquant_disaster_recovery.errors import DRNotFoundError
from apexquant_disaster_recovery.health import HealthChecker
from apexquant_disaster_recovery.models import (
    BackupRequirementStatus,
    HealthCheckStatus,
    PlanStatus,
    ReadinessReport,
    RecoveryComponent,
    RecoveryPlan,
    RecoveryStrategy,
)
from apexquant_disaster_recovery.repository import DRRepository
from apexquant_disaster_recovery.scoring import score_readiness
from apexquant_disaster_recovery.models import utc_now


class CheckResult:
    def __init__(self, ok: bool, result: dict | None = None, error: str | None = None) -> None:
        self.ok = ok
        self.result = result or {}
        self.error = error


class DRVerifier:
    def __init__(
        self,
        repository: DRRepository,
        backup_provider: BackupStatusProvider,
        health_checker: HealthChecker,
        enable_health_checks: bool = True,
    ) -> None:
        self._repository = repository
        self._backup_provider = backup_provider
        self._health_checker = health_checker
        self._enable_health_checks = enable_health_checks

    def get_active_plan_or_fail(self, plan_id) -> RecoveryPlan:
        plan = self._repository.get_plan(plan_id)

        if plan is None:
            raise DRNotFoundError(f"plan not found: {plan_id}")

        return plan

    def validate_plan(self, plan_id) -> CheckResult:
        try:
            plan = self.get_active_plan_or_fail(plan_id)
        except DRNotFoundError as exc:
            return CheckResult(False, error=str(exc))

        if plan.status != PlanStatus.ACTIVE:
            return CheckResult(
                False,
                {
                    "plan_status": plan.status.value,
                },
                "plan is not ACTIVE",
            )

        components = self._repository.list_components(plan.plan_id)

        if not components:
            return CheckResult(
                False,
                {},
                "plan has no recovery components",
            )

        return CheckResult(
            True,
            {
                "plan_id": str(plan.plan_id),
                "plan_status": plan.status.value,
                "component_count": len(components),
            },
        )

    def assess_backup_requirements(
        self,
        plan: RecoveryPlan,
    ) -> list[BackupRequirementStatus]:
        components = self._repository.list_components(plan.plan_id)

        requirements: list[BackupRequirementStatus] = []

        for component in components:
            requires_backup = (
                component.recovery_strategy == RecoveryStrategy.RESTORE_FROM_BACKUP
            )

            requirement = BackupRequirementStatus(
                component_name=component.component_name,
                backup_policy_name=component.backup_policy_name,
                required=requires_backup,
                policy_exists=False,
                latest_backup_at=None,
                fresh=False,
                verified=False,
                rpo_seconds=component.rpo_seconds or plan.rpo_seconds,
            )

            if not requires_backup:
                requirements.append(requirement)
                continue

            if component.backup_policy_name is None:
                requirements.append(requirement)
                continue

            requirement.policy_exists = self._backup_provider.policy_exists(
                component.backup_policy_name
            )

            if not requirement.policy_exists:
                requirements.append(requirement)
                continue

            backup_status = self._backup_provider.latest_backup(
                component.backup_policy_name
            )

            if backup_status is None or backup_status.latest_success_at is None:
                requirements.append(requirement)
                continue

            requirement.latest_backup_at = backup_status.latest_success_at

            rpo_seconds = component.rpo_seconds or plan.rpo_seconds
            freshness_cutoff = utc_now() - timedelta(seconds=rpo_seconds)

            requirement.fresh = backup_status.latest_success_at >= freshness_cutoff

            requirement.verified = (
                backup_status.verification_status == "SUCCEEDED"
            )

            requirements.append(requirement)

        return requirements

    def check_backup_policies(
        self,
        plan: RecoveryPlan,
        requirements: list[BackupRequirementStatus],
    ) -> CheckResult:
        missing_policy = [
            requirement.component_name
            for requirement in requirements
            if requirement.required and not requirement.policy_exists
        ]

        if missing_policy:
            return CheckResult(
                False,
                {"missing_backup_policy_for": missing_policy},
                "one or more components are missing backup policies",
            )

        return CheckResult(
            True,
            {"required_backup_components": len([r for r in requirements if r.required])},
        )

    def check_backup_freshness(
        self,
        plan: RecoveryPlan,
        requirements: list[BackupRequirementStatus],
    ) -> CheckResult:
        stale = [
            requirement.component_name
            for requirement in requirements
            if requirement.required and requirement.policy_exists and not requirement.fresh
        ]

        if stale:
            return CheckResult(
                False,
                {"stale_or_missing_backups_for": stale},
                "one or more required backups are missing or stale",
            )

        return CheckResult(True, {"all_required_backups_fresh": True})

    def check_backup_verification(
        self,
        plan: RecoveryPlan,
        requirements: list[BackupRequirementStatus],
    ) -> CheckResult:
        unverified = [
            requirement.component_name
            for requirement in requirements
            if requirement.required
            and requirement.policy_exists
            and requirement.fresh
            and not requirement.verified
        ]

        if unverified:
            return CheckResult(
                False,
                {"unverified_backups_for": unverified},
                "one or more required backups are not verified",
            )

        return CheckResult(True, {"all_required_backups_verified": True})

    def check_health(self, plan: RecoveryPlan) -> tuple[CheckResult, list[HealthCheckStatus]]:
        components = self._repository.list_components(plan.plan_id)

        checks: list[HealthCheckStatus] = []
        failed: list[str] = []

        for component in components:
            health_status = HealthCheckStatus(
                component_name=component.component_name,
                health_endpoint=component.health_endpoint,
                applicable=bool(component.health_endpoint),
                checked=False,
                healthy=None,
            )

            if not component.health_endpoint:
                checks.append(health_status)
                continue

            if not self._enable_health_checks:
                health_status.checked = False
                health_status.healthy = None
                checks.append(health_status)
                continue

            healthy = self._health_checker.check(component)

            health_status.checked = True
            health_status.healthy = healthy

            if healthy is False:
                failed.append(component.component_name)

            checks.append(health_status)

        if failed:
            return CheckResult(
                False,
                {"failed_health_checks_for": failed},
                "one or more component health checks failed",
            ), checks

        return CheckResult(True, {"health_checks_passed": True}), checks

    def build_readiness_report(self, plan_id) -> ReadinessReport:
        plan = self.get_active_plan_or_fail(plan_id)

        backup_requirements = self.assess_backup_requirements(plan)
        health_check_result, health_checks = self.check_health(plan)

        recent_drill_passed = self._repository.latest_passed_drill_within_days(
            plan.plan_id,
            plan.drill_max_age_days,
        )

        score, state, fail_closed_triggered = score_readiness(
            plan_active=plan.status == PlanStatus.ACTIVE,
            backup_requirements=backup_requirements,
            health_checks=health_checks,
            recent_drill_passed=recent_drill_passed,
        )

        warnings: list[str] = []

        if plan.status != PlanStatus.ACTIVE:
            warnings.append("recovery plan is not active")

        for requirement in backup_requirements:
            if requirement.required and not requirement.policy_exists:
                warnings.append(
                    f"component {requirement.component_name} has no backup policy"
                )

            if requirement.required and requirement.policy_exists and not requirement.fresh:
                warnings.append(
                    f"component {requirement.component_name} backup is stale or missing"
                )

            if requirement.required and requirement.fresh and not requirement.verified:
                warnings.append(
                    f"component {requirement.component_name} backup is not verified"
                )

        for health_check in health_checks:
            if health_check.applicable and health_check.healthy is False:
                warnings.append(
                    f"component {health_check.component_name} failed health check"
                )

        return ReadinessReport(
            plan_id=plan.plan_id,
            environment=plan.environment,
            plan_active=plan.status == PlanStatus.ACTIVE,
            score=score,
            state=state,
            fail_closed_triggered=fail_closed_triggered,
            backup_requirements=backup_requirements,
            health_checks=health_checks,
            recent_drill_passed=recent_drill_passed,
            warnings=warnings,
        )