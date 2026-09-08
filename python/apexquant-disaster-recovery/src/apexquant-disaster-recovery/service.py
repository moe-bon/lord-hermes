from __future__ import annotations

from apexquant_disaster_recovery.backup_provider import BackupStatusProvider
from apexquant_disaster_recovery.drill_engine import DrillEngine
from apexquant_disaster_recovery.errors import DRNotFoundError, DRStateError
from apexquant_disaster_recovery.health import HealthChecker
from apexquant_disaster_recovery.models import (
    ComponentType,
    DREvent,
    PlanStatus,
    RecoveryComponent,
    RecoveryPlan,
    RecoveryStrategy,
)
from apexquant_disaster_recovery.repository import DRRepository
from apexquant_disaster_recovery.verifier import DRVerifier

DEFAULT_PLAN_NAME = "platform-disaster-recovery-plan"


class DisasterRecoveryService:
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
        self._verifier = DRVerifier(
            repository=repository,
            backup_provider=backup_provider,
            health_checker=health_checker,
            enable_health_checks=enable_health_checks,
        )
        self._drill_engine = DrillEngine(repository, self._verifier)

    def create_plan(self, plan: RecoveryPlan, actor: str = "system") -> RecoveryPlan:
        created = self._repository.create_plan(plan)

        self._repository.record_event(
            DREvent(
                plan_id=created.plan_id,
                event_type="DR_PLAN_CREATED",
                actor=actor,
                reason="disaster recovery plan created",
                details=created.model_dump(mode="json"),
            )
        )

        return created

    def activate_plan(self, plan_id, actor: str = "system") -> RecoveryPlan:
        plan = self._repository.get_plan(plan_id)

        if plan is None:
            raise DRNotFoundError(f"plan not found: {plan_id}")

        if plan.status == PlanStatus.RETIRED:
            raise DRStateError("retired plans cannot be activated")

        self._repository.update_plan_status(plan_id, PlanStatus.ACTIVE)

        self._repository.record_event(
            DREvent(
                plan_id=plan_id,
                event_type="DR_PLAN_ACTIVATED",
                actor=actor,
                reason="disaster recovery plan activated",
            )
        )

        return self._repository.get_plan(plan_id)

    def add_component(
        self,
        plan_id,
        component: RecoveryComponent,
        actor: str = "system",
    ) -> RecoveryComponent:
        plan = self._repository.get_plan(plan_id)

        if plan is None:
            raise DRNotFoundError(f"plan not found: {plan_id}")

        component.plan_id = plan_id

        created = self._repository.add_component(component)

        self._repository.record_event(
            DREvent(
                plan_id=plan_id,
                event_type="DR_COMPONENT_ADDED",
                actor=actor,
                reason=f"component added: {component.component_name}",
                details=created.model_dump(mode="json"),
            )
        )

        return created

    def bootstrap_default_plan(
        self,
        environment: str,
        backup_policy_name: str,
        actor: str = "system",
    ) -> RecoveryPlan:
        existing = self._repository.get_plan_by_name(DEFAULT_PLAN_NAME)

        if existing is not None:
            return existing

        plan = RecoveryPlan(
            name=DEFAULT_PLAN_NAME,
            environment=environment,
            description="Canonical ApexQuant Ultra platform disaster recovery plan",
            criticality_tier="TIER_1",
            rpo_seconds=3600,
            rto_seconds=3600,
            drill_max_age_days=7,
            status=PlanStatus.DRAFT,
        )

        plan = self.create_plan(plan, actor=actor)

        components = [
            RecoveryComponent(
                component_name="postgresql-primary",
                component_type=ComponentType.DATABASE,
                recovery_strategy=RecoveryStrategy.RESTORE_FROM_BACKUP,
                priority=1,
                backup_policy_name=backup_policy_name,
                rpo_seconds=plan.rpo_seconds,
                rto_seconds=plan.rto_seconds,
                notes="Primary PostgreSQL transactional truth database",
            ),
            RecoveryComponent(
                component_name="backup-object-storage",
                component_type=ComponentType.OBJECT_STORAGE,
                recovery_strategy=RecoveryStrategy.MANUAL,
                priority=2,
                backup_policy_name=None,
                notes="Backup artifact storage. Requires storage-provider recovery or replication.",
            ),
            RecoveryComponent(
                component_name="event-bus",
                component_type=ComponentType.EVENT_BUS,
                recovery_strategy=RecoveryStrategy.REBUILD,
                priority=3,
                backup_policy_name=None,
                notes="Kafka/Redpanda event backbone. Rebuild and replay from durable sources.",
            ),
            RecoveryComponent(
                component_name="redis-cache",
                component_type=ComponentType.REDIS,
                recovery_strategy=RecoveryStrategy.REBUILD,
                priority=4,
                backup_policy_name=None,
                notes="Redis cache and temporary state. Rebuild from transactional truth.",
            ),
            RecoveryComponent(
                component_name="backup-recovery-core",
                component_type=ComponentType.SERVICE,
                recovery_strategy=RecoveryStrategy.RESTART,
                priority=5,
                backup_policy_name=None,
                health_endpoint="http://backup-recovery-core:8093/healthz",
                notes="Backup and recovery control service",
            ),
            RecoveryComponent(
                component_name="disaster-recovery-core",
                component_type=ComponentType.SERVICE,
                recovery_strategy=RecoveryStrategy.RESTART,
                priority=6,
                backup_policy_name=None,
                health_endpoint="http://disaster-recovery-core:8094/healthz",
                notes="Disaster recovery control service",
            ),
        ]

        for component in components:
            self.add_component(plan.plan_id, component, actor=actor)

        return self.activate_plan(plan.plan_id, actor=actor)

    def readiness(self, plan_id):
        return self._verifier.build_readiness_report(plan_id)

    def run_drill(self, plan_id, actor: str = "system", trigger: str = "manual"):
        return self._drill_engine.run_drill(plan_id, actor=actor, trigger=trigger)

    def status(self) -> dict:
        plans = self._repository.list_plans()

        summaries = []

        for plan in plans:
            latest_drills = self._repository.list_drills(plan.plan_id, limit=1)

            summaries.append(
                {
                    "plan_id": str(plan.plan_id),
                    "name": plan.name,
                    "environment": plan.environment,
                    "status": plan.status.value,
                    "latest_drill": (
                        latest_drills[0].model_dump(mode="json")
                        if latest_drills
                        else None
                    ),
                }
            )

        return {"plans": summaries}