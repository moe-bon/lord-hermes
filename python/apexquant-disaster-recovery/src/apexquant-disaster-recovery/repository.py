from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from apexquant_disaster_recovery.errors import DRNotFoundError
from apexquant_disaster_recovery.models import (
    Drill,
    DrillStatus,
    DrillStep,
    DREvent,
    PlanStatus,
    RecoveryComponent,
    RecoveryPlan,
    StepStatus,
    new_uuid,
    utc_now,
)


class DRRepositoryError(Exception):
    pass


def apply_migrations(database_url: str, migrations_dir: str) -> None:
    path = Path(migrations_dir)

    if not path.exists():
        raise DRRepositoryError(f"migrations directory does not exist: {path}")

    migrations = sorted(path.glob("*.sql"))

    if not migrations:
        raise DRRepositoryError(f"no SQL migrations found in {path}")

    with psycopg.connect(database_url, autocommit=True) as conn:
        for migration in migrations:
            conn.execute(migration.read_text(encoding="utf-8"))


class DRRepository(Protocol):
    def create_plan(self, plan: RecoveryPlan) -> RecoveryPlan:
        raise NotImplementedError

    def get_plan(self, plan_id: UUID) -> RecoveryPlan | None:
        raise NotImplementedError

    def get_plan_by_name(self, name: str) -> RecoveryPlan | None:
        raise NotImplementedError

    def list_plans(self) -> list[RecoveryPlan]:
        raise NotImplementedError

    def update_plan_status(self, plan_id: UUID, status: PlanStatus) -> None:
        raise NotImplementedError

    def add_component(self, component: RecoveryComponent) -> RecoveryComponent:
        raise NotImplementedError

    def list_components(self, plan_id: UUID) -> list[RecoveryComponent]:
        raise NotImplementedError

    def create_drill(self, drill: Drill) -> Drill:
        raise NotImplementedError

    def update_drill(self, drill: Drill) -> None:
        raise NotImplementedError

    def get_drill(self, drill_id: UUID) -> Drill | None:
        raise NotImplementedError

    def list_drills(self, plan_id: UUID | None = None, limit: int = 100) -> list[Drill]:
        raise NotImplementedError

    def latest_passed_drill_within_days(
        self,
        plan_id: UUID,
        days: int | None,
    ) -> bool:
        raise NotImplementedError

    def create_step(self, step: DrillStep) -> DrillStep:
        raise NotImplementedError

    def update_step(self, step: DrillStep) -> None:
        raise NotImplementedError

    def list_steps(self, drill_id: UUID) -> list[DrillStep]:
        raise NotImplementedError

    def record_event(self, event: DREvent) -> DREvent:
        raise NotImplementedError


class InMemoryDRRepository:
    def __init__(self) -> None:
        self._plans: dict[UUID, RecoveryPlan] = {}
        self._components: dict[UUID, list[RecoveryComponent]] = {}
        self._drills: dict[UUID, Drill] = {}
        self._steps: dict[UUID, list[DrillStep]] = {}
        self._events: list[DREvent] = []

    def create_plan(self, plan: RecoveryPlan) -> RecoveryPlan:
        if plan.plan_id is None:
            plan.plan_id = new_uuid()

        now = utc_now()

        plan.created_at = plan.created_at or now
        plan.updated_at = now

        self._plans[plan.plan_id] = plan
        self._components.setdefault(plan.plan_id, [])

        return plan

    def get_plan(self, plan_id: UUID) -> RecoveryPlan | None:
        return self._plans.get(plan_id)

    def get_plan_by_name(self, name: str) -> RecoveryPlan | None:
        for plan in self._plans.values():
            if plan.name == name:
                return plan

        return None

    def list_plans(self) -> list[RecoveryPlan]:
        return sorted(self._plans.values(), key=lambda plan: plan.name)

    def update_plan_status(self, plan_id: UUID, status: PlanStatus) -> None:
        plan = self._plans.get(plan_id)

        if plan is None:
            raise DRNotFoundError(f"plan not found: {plan_id}")

        plan.status = status
        plan.updated_at = utc_now()

    def add_component(self, component: RecoveryComponent) -> RecoveryComponent:
        if component.plan_id is None:
            raise DRRepositoryError("component.plan_id is required")

        if component.plan_id not in self._plans:
            raise DRNotFoundError(f"plan not found: {component.plan_id}")

        if component.component_id is None:
            component.component_id = new_uuid()

        self._components.setdefault(component.plan_id, [])

        for existing in self._components[component.plan_id]:
            if existing.component_name == component.component_name:
                raise DRRepositoryError(
                    f"component already exists: {component.component_name}"
                )

        self._components[component.plan_id].append(component)

        return component

    def list_components(self, plan_id: UUID) -> list[RecoveryComponent]:
        components = self._components.get(plan_id, [])

        return sorted(components, key=lambda component: component.priority)

    def create_drill(self, drill: Drill) -> Drill:
        if drill.drill_id is None:
            drill.drill_id = new_uuid()

        self._drills[drill.drill_id] = drill
        self._steps.setdefault(drill.drill_id, [])

        return drill

    def update_drill(self, drill: Drill) -> None:
        if drill.drill_id is None:
            raise DRRepositoryError("drill.drill_id is required")

        self._drills[drill.drill_id] = drill

    def get_drill(self, drill_id: UUID) -> Drill | None:
        return self._drills.get(drill_id)

    def list_drills(self, plan_id: UUID | None = None, limit: int = 100) -> list[Drill]:
        drills = list(self._drills.values())

        if plan_id is not None:
            drills = [drill for drill in drills if drill.plan_id == plan_id]

        drills.sort(key=lambda drill: drill.started_at, reverse=True)

        return drills[:limit]

    def latest_passed_drill_within_days(
        self,
        plan_id: UUID,
        days: int | None,
    ) -> bool:
        drills = [
            drill
            for drill in self._drills.values()
            if drill.plan_id == plan_id and drill.status == DrillStatus.SUCCEEDED
        ]

        if not drills:
            return False

        latest = max(drills, key=lambda drill: drill.completed_at or drill.started_at)

        if days is None:
            return True

        completed_at = latest.completed_at or latest.started_at

        if completed_at is None:
            return False

        return completed_at >= utc_now() - timedelta(days=days)

    def create_step(self, step: DrillStep) -> DrillStep:
        if step.drill_id is None:
            raise DRRepositoryError("step.drill_id is required")

        if step.step_id is None:
            step.step_id = new_uuid()

        self._steps.setdefault(step.drill_id, [])
        self._steps[step.drill_id].append(step)

        return step

    def update_step(self, step: DrillStep) -> None:
        if step.drill_id is None or step.step_id is None:
            raise DRRepositoryError("step.drill_id and step.step_id are required")

        steps = self._steps.get(step.drill_id, [])

        for index, existing in enumerate(steps):
            if existing.step_id == step.step_id:
                steps[index] = step
                return

        raise DRNotFoundError(f"step not found: {step.step_id}")

    def list_steps(self, drill_id: UUID) -> list[DrillStep]:
        steps = self._steps.get(drill_id, [])

        return sorted(steps, key=lambda step: step.step_order)

    def record_event(self, event: DREvent) -> DREvent:
        if event.event_id is None:
            event.event_id = new_uuid()

        self._events.append(event)

        return event


class PostgresDRRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def _plan_from_row(self, row) -> RecoveryPlan:
        return RecoveryPlan(
            plan_id=row[0],
            name=row[1],
            environment=row[2],
            description=row[3],
            criticality_tier=row[4],
            rpo_seconds=row[5],
            rto_seconds=row[6],
            drill_max_age_days=row[7],
            status=PlanStatus(row[8]),
            created_at=row[9],
            updated_at=row[10],
        )

    def _component_from_row(self, row) -> RecoveryComponent:
        return RecoveryComponent(
            component_id=row[0],
            plan_id=row[1],
            component_name=row[2],
            component_type=row[3],
            recovery_strategy=row[4],
            priority=row[5],
            backup_policy_name=row[6],
            health_endpoint=row[7],
            rpo_seconds=row[8],
            rto_seconds=row[9],
            notes=row[10],
        )

    def _drill_from_row(self, row) -> Drill:
        return Drill(
            drill_id=row[0],
            plan_id=row[1],
            environment=row[2],
            trigger=row[3],
            actor=row[4],
            status=DrillStatus(row[5]),
            started_at=row[6],
            completed_at=row[7],
            readiness_score=float(row[8]) if row[8] is not None else None,
            result=row[9],
            error=row[10],
        )

    def _step_from_row(self, row) -> DrillStep:
        return DrillStep(
            step_id=row[0],
            drill_id=row[1],
            step_name=row[2],
            step_order=row[3],
            status=StepStatus(row[4]),
            started_at=row[5],
            completed_at=row[6],
            result=row[7],
            error=row[8],
        )

    def create_plan(self, plan: RecoveryPlan) -> RecoveryPlan:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO disaster_recovery.recovery_plans (
                    name,
                    environment,
                    description,
                    criticality_tier,
                    rpo_seconds,
                    rto_seconds,
                    drill_max_age_days,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING
                    plan_id,
                    name,
                    environment,
                    description,
                    criticality_tier,
                    rpo_seconds,
                    rto_seconds,
                    drill_max_age_days,
                    status,
                    created_at,
                    updated_at
                """,
                (
                    plan.name,
                    plan.environment,
                    plan.description,
                    plan.criticality_tier,
                    plan.rpo_seconds,
                    plan.rto_seconds,
                    plan.drill_max_age_days,
                    plan.status.value,
                ),
            ).fetchone()

        return self._plan_from_row(row)

    def get_plan(self, plan_id: UUID) -> RecoveryPlan | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    plan_id,
                    name,
                    environment,
                    description,
                    criticality_tier,
                    rpo_seconds,
                    rto_seconds,
                    drill_max_age_days,
                    status,
                    created_at,
                    updated_at
                FROM disaster_recovery.recovery_plans
                WHERE plan_id = %s
                """,
                (plan_id,),
            ).fetchone()

        if row is None:
            return None

        return self._plan_from_row(row)

    def get_plan_by_name(self, name: str) -> RecoveryPlan | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    plan_id,
                    name,
                    environment,
                    description,
                    criticality_tier,
                    rpo_seconds,
                    rto_seconds,
                    drill_max_age_days,
                    status,
                    created_at,
                    updated_at
                FROM disaster_recovery.recovery_plans
                WHERE name = %s
                """,
                (name,),
            ).fetchone()

        if row is None:
            return None

        return self._plan_from_row(row)

    def list_plans(self) -> list[RecoveryPlan]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    plan_id,
                    name,
                    environment,
                    description,
                    criticality_tier,
                    rpo_seconds,
                    rto_seconds,
                    drill_max_age_days,
                    status,
                    created_at,
                    updated_at
                FROM disaster_recovery.recovery_plans
                ORDER BY name
                """
            ).fetchall()

        return [self._plan_from_row(row) for row in rows]

    def update_plan_status(self, plan_id: UUID, status: PlanStatus) -> None:
        with self._pool.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE disaster_recovery.recovery_plans
                SET
                    status = %s,
                    updated_at = now()
                WHERE plan_id = %s
                """,
                (status.value, plan_id),
            )

            if cursor.rowcount == 0:
                raise DRNotFoundError(f"plan not found: {plan_id}")

    def add_component(self, component: RecoveryComponent) -> RecoveryComponent:
        if component.plan_id is None:
            raise DRRepositoryError("component.plan_id is required")

        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO disaster_recovery.recovery_components (
                    plan_id,
                    component_name,
                    component_type,
                    recovery_strategy,
                    priority,
                    backup_policy_name,
                    health_endpoint,
                    rpo_seconds,
                    rto_seconds,
                    notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING
                    component_id,
                    plan_id,
                    component_name,
                    component_type,
                    recovery_strategy,
                    priority,
                    backup_policy_name,
                    health_endpoint,
                    rpo_seconds,
                    rto_seconds,
                    notes
                """,
                (
                    component.plan_id,
                    component.component_name,
                    component.component_type.value,
                    component.recovery_strategy.value,
                    component.priority,
                    component.backup_policy_name,
                    component.health_endpoint,
                    component.rpo_seconds,
                    component.rto_seconds,
                    component.notes,
                ),
            ).fetchone()

        return self._component_from_row(row)

    def list_components(self, plan_id: UUID) -> list[RecoveryComponent]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    component_id,
                    plan_id,
                    component_name,
                    component_type,
                    recovery_strategy,
                    priority,
                    backup_policy_name,
                    health_endpoint,
                    rpo_seconds,
                    rto_seconds,
                    notes
                FROM disaster_recovery.recovery_components
                WHERE plan_id = %s
                ORDER BY priority, component_name
                """,
                (plan_id,),
            ).fetchall()

        return [self._component_from_row(row) for row in rows]

    def create_drill(self, drill: Drill) -> Drill:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO disaster_recovery.dr_drills (
                    plan_id,
                    environment,
                    trigger,
                    actor,
                    status,
                    started_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING
                    drill_id,
                    plan_id,
                    environment,
                    trigger,
                    actor,
                    status,
                    started_at,
                    completed_at,
                    readiness_score,
                    result,
                    error
                """,
                (
                    drill.plan_id,
                    drill.environment,
                    drill.trigger,
                    drill.actor,
                    drill.status.value,
                    drill.started_at,
                ),
            ).fetchone()

        return self._drill_from_row(row)

    def update_drill(self, drill: Drill) -> None:
        if drill.drill_id is None:
            raise DRRepositoryError("drill.drill_id is required")

        with self._pool.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE disaster_recovery.dr_drills
                SET
                    status = %s,
                    completed_at = %s,
                    readiness_score = %s,
                    result = %s,
                    error = %s
                WHERE drill_id = %s
                """,
                (
                    drill.status.value,
                    drill.completed_at,
                    drill.readiness_score,
                    Json(drill.result),
                    drill.error,
                    drill.drill_id,
                ),
            )

            if cursor.rowcount == 0:
                raise DRNotFoundError(f"drill not found: {drill.drill_id}")

    def get_drill(self, drill_id: UUID) -> Drill | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    drill_id,
                    plan_id,
                    environment,
                    trigger,
                    actor,
                    status,
                    started_at,
                    completed_at,
                    readiness_score,
                    result,
                    error
                FROM disaster_recovery.dr_drills
                WHERE drill_id = %s
                """,
                (drill_id,),
            ).fetchone()

        if row is None:
            return None

        return self._drill_from_row(row)

    def list_drills(self, plan_id: UUID | None = None, limit: int = 100) -> list[Drill]:
        with self._pool.connection() as conn:
            if plan_id is None:
                rows = conn.execute(
                    """
                    SELECT
                        drill_id,
                        plan_id,
                        environment,
                        trigger,
                        actor,
                        status,
                        started_at,
                        completed_at,
                        readiness_score,
                        result,
                        error
                    FROM disaster_recovery.dr_drills
                    ORDER BY started_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT
                        drill_id,
                        plan_id,
                        environment,
                        trigger,
                        actor,
                        status,
                        started_at,
                        completed_at,
                        readiness_score,
                        result,
                        error
                    FROM disaster_recovery.dr_drills
                    WHERE plan_id = %s
                    ORDER BY started_at DESC
                    LIMIT %s
                    """,
                    (plan_id, limit),
                ).fetchall()

        return [self._drill_from_row(row) for row in rows]

    def latest_passed_drill_within_days(
        self,
        plan_id: UUID,
        days: int | None,
    ) -> bool:
        with self._pool.connection() as conn:
            if days is None:
                row = conn.execute(
                    """
                    SELECT 1
                    FROM disaster_recovery.dr_drills
                    WHERE plan_id = %s
                      AND status = 'SUCCEEDED'
                    ORDER BY COALESCE(completed_at, started_at) DESC
                    LIMIT 1
                    """,
                    (plan_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT 1
                    FROM disaster_recovery.dr_drills
                    WHERE plan_id = %s
                      AND status = 'SUCCEEDED'
                      AND COALESCE(completed_at, started_at) >= now() - make_interval(days => %s)
                    ORDER BY COALESCE(completed_at, started_at) DESC
                    LIMIT 1
                    """,
                    (plan_id, days),
                ).fetchone()

        return row is not None

    def create_step(self, step: DrillStep) -> DrillStep:
        if step.drill_id is None:
            raise DRRepositoryError("step.drill_id is required")

        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO disaster_recovery.dr_drill_steps (
                    drill_id,
                    step_name,
                    step_order,
                    status,
                    started_at,
                    result
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING
                    step_id,
                    drill_id,
                    step_name,
                    step_order,
                    status,
                    started_at,
                    completed_at,
                    result,
                    error
                """,
                (
                    step.drill_id,
                    step.step_name,
                    step.step_order,
                    step.status.value,
                    step.started_at,
                    Json(step.result),
                ),
            ).fetchone()

        return self._step_from_row(row)

    def update_step(self, step: DrillStep) -> None:
        if step.step_id is None:
            raise DRRepositoryError("step.step_id is required")

        with self._pool.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE disaster_recovery.dr_drill_steps
                SET
                    status = %s,
                    completed_at = %s,
                    result = %s,
                    error = %s
                WHERE step_id = %s
                """,
                (
                    step.status.value,
                    step.completed_at,
                    Json(step.result),
                    step.error,
                    step.step_id,
                ),
            )

            if cursor.rowcount == 0:
                raise DRNotFoundError(f"step not found: {step.step_id}")

    def list_steps(self, drill_id: UUID) -> list[DrillStep]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    step_id,
                    drill_id,
                    step_name,
                    step_order,
                    status,
                    started_at,
                    completed_at,
                    result,
                    error
                FROM disaster_recovery.dr_drill_steps
                WHERE drill_id = %s
                ORDER BY step_order
                """,
                (drill_id,),
            ).fetchall()

        return [self._step_from_row(row) for row in rows]

    def record_event(self, event: DREvent) -> DREvent:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO disaster_recovery.dr_events (
                    plan_id,
                    drill_id,
                    event_type,
                    severity,
                    actor,
                    reason,
                    details,
                    occurred_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING
                    event_id,
                    plan_id,
                    drill_id,
                    event_type,
                    severity,
                    actor,
                    reason,
                    details,
                    occurred_at
                """,
                (
                    event.plan_id,
                    event.drill_id,
                    event.event_type,
                    event.severity,
                    event.actor,
                    event.reason,
                    Json(event.details),
                    event.occurred_at,
                ),
            ).fetchone()

        return DREvent(
            event_id=row[0],
            plan_id=row[1],
            drill_id=row[2],
            event_type=row[3],
            severity=row[4],
            actor=row[5],
            reason=row[6],
            details=row[7],
            occurred_at=row[8],
        )