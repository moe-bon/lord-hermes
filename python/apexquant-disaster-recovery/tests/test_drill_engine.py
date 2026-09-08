from datetime import timedelta

from apexquant_disaster_recovery.backup_provider import InMemoryBackupStatusProvider
from apexquant_disaster_recovery.drill_engine import DrillEngine
from apexquant_disaster_recovery.health import NullHealthChecker
from apexquant_disaster_recovery.models import (
    BackupStatus,
    ComponentType,
    PlanStatus,
    RecoveryComponent,
    RecoveryPlan,
    RecoveryStrategy,
    utc_now,
)
from apexquant_disaster_recovery.repository import InMemoryDRRepository
from apexquant_disaster_recovery.verifier import DRVerifier


def build_environment(with_backup: bool):
    repository = InMemoryDRRepository()
    backup_provider = InMemoryBackupStatusProvider()
    health_checker = NullHealthChecker()

    plan = RecoveryPlan(
        name="platform-disaster-recovery-plan",
        environment="local",
        rpo_seconds=3600,
        rto_seconds=3600,
        status=PlanStatus.ACTIVE,
    )

    plan = repository.create_plan(plan)

    repository.add_component(
        RecoveryComponent(
            plan_id=plan.plan_id,
            component_name="postgresql-primary",
            component_type=ComponentType.DATABASE,
            recovery_strategy=RecoveryStrategy.RESTORE_FROM_BACKUP,
            priority=1,
            backup_policy_name="local-postgres",
            rpo_seconds=3600,
            rto_seconds=3600,
        )
    )

    if with_backup:
        backup_provider.add_policy("local-postgres")
        backup_provider.set_latest_backup(
            BackupStatus(
                policy_name="local-postgres",
                latest_success_at=utc_now() - timedelta(minutes=5),
                latest_artifact_uri="file:///backups/apexquant-backups/postgres/run.dump",
                verification_status="SUCCEEDED",
                last_verified_at=utc_now() - timedelta(minutes=4),
            )
        )

    verifier = DRVerifier(
        repository=repository,
        backup_provider=backup_provider,
        health_checker=health_checker,
        enable_health_checks=False,
    )

    engine = DrillEngine(repository=repository, verifier=verifier)

    return repository, engine, plan


def test_drill_succeeds_when_backup_is_fresh_and_verified() -> None:
    repository, engine, plan = build_environment(with_backup=True)

    drill = engine.run_drill(plan.plan_id, actor="test")

    assert drill.status.value == "SUCCEEDED"
    assert drill.readiness_score is not None
    assert drill.readiness_score >= 90.0


def test_drill_fails_when_backup_missing() -> None:
    repository, engine, plan = build_environment(with_backup=False)

    drill = engine.run_drill(plan.plan_id, actor="test")

    assert drill.status.value == "FAILED"
    assert drill.readiness_score is not None
    assert drill.readiness_score <= 49.0