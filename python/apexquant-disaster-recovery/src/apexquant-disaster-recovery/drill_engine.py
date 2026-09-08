from __future__ import annotations

from typing import Callable

from apexquant_disaster_recovery.errors import DRDrillError, DRNotFoundError
from apexquant_disaster_recovery.models import (
    Drill,
    DrillStatus,
    DrillStep,
    StepStatus,
    utc_now,
)
from apexquant_disaster_recovery.repository import DRRepository
from apexquant_disaster_recovery.verifier import CheckResult, DRVerifier

MINIMUM_SUCCESS_SCORE = 70.0


class DrillEngine:
    def __init__(self, repository: DRRepository, verifier: DRVerifier) -> None:
        self._repository = repository
        self._verifier = verifier

    def run_drill(
        self,
        plan_id,
        actor: str,
        trigger: str = "manual",
    ) -> Drill:
        plan = self._repository.get_plan(plan_id)

        if plan is None:
            raise DRNotFoundError(f"plan not found: {plan_id}")

        drill = Drill(
            plan_id=plan.plan_id,
            environment=plan.environment,
            trigger=trigger,
            actor=actor,
            status=DrillStatus.RUNNING,
        )

        drill = self._repository.create_drill(drill)

        failed = False
        stop_drill = False

        steps: list[tuple[str, Callable[[], CheckResult]]] = [
            ("validate_plan", lambda: self._verifier.validate_plan(plan.plan_id)),
        ]

        backup_requirements = self._verifier.assess_backup_requirements(plan)

        steps.extend(
            [
                (
                    "check_backup_policies",
                    lambda: self._verifier.check_backup_policies(plan, backup_requirements),
                ),
                (
                    "check_backup_freshness",
                    lambda: self._verifier.check_backup_freshness(plan, backup_requirements),
                ),
                (
                    "check_backup_verification",
                    lambda: self._verifier.check_backup_verification(plan, backup_requirements),
                ),
            ]
        )

        def health_step() -> CheckResult:
            result, _ = self._verifier.check_health(plan)
            return result

        steps.append(("check_component_health", health_step))

        for order, (step_name, step_fn) in enumerate(steps, start=1):
            if stop_drill:
                break

            step = DrillStep(
                drill_id=drill.drill_id,
                step_name=step_name,
                step_order=order,
                status=StepStatus.RUNNING,
                started_at=utc_now(),
            )

            step = self._repository.create_step(step)

            try:
                result = step_fn()

                step.completed_at = utc_now()
                step.result = result.result

                if result.ok:
                    step.status = StepStatus.SUCCEEDED
                else:
                    step.status = StepStatus.FAILED
                    step.error = result.error
                    failed = True

                    if step_name == "validate_plan":
                        stop_drill = True

            except Exception as exc:
                step.completed_at = utc_now()
                step.status = StepStatus.FAILED
                step.error = str(exc)
                failed = True

                if step_name == "validate_plan":
                    stop_drill = True

            self._repository.update_step(step)

        readiness = self._verifier.build_readiness_report(plan.plan_id)

        drill_completed = not failed and readiness.score >= MINIMUM_SUCCESS_SCORE

        drill.status = DrillStatus.SUCCEEDED if drill_completed else DrillStatus.FAILED
        drill.completed_at = utc_now()
        drill.readiness_score = readiness.score
        drill.result = readiness.model_dump(mode="json")

        if failed:
            drill.error = "one or more drill steps failed"

        self._repository.update_drill(drill)

        self._repository.record_event(
            {
                "plan_id": plan.plan_id,
                "drill_id": drill.drill_id,
                "event_type": "DR_DRILL_COMPLETED",
                "severity": "INFO" if drill_completed else "WARNING",
                "actor": actor,
                "reason": drill.error or "drill completed",
                "details": {
                    "status": drill.status.value,
                    "readiness_score": readiness.score,
                },
            }
        )

        return drill