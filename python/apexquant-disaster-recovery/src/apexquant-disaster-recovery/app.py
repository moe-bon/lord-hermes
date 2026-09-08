from __future__ import annotations

from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse
from apexquant_disaster_recovery.errors import (
    DisasterRecoveryError,
    DRNotFoundError,
)
from apexquant_disaster_recovery.models import (
    ComponentType,
    PlanStatus,
    RecoveryComponent,
    RecoveryPlan,
    RecoveryStrategy,
)
from apexquant_disaster_recovery.service import DisasterRecoveryService


class PlanCreateRequest(BaseModel):
    name: str
    environment: str
    description: str = ""
    criticality_tier: str = "TIER_1"
    rpo_seconds: int = Field(gt=0)
    rto_seconds: int = Field(gt=0)
    drill_max_age_days: int | None = Field(default=7, gt=0)


class ComponentCreateRequest(BaseModel):
    component_name: str
    component_type: ComponentType
    recovery_strategy: RecoveryStrategy
    priority: int = Field(default=100, gt=0)
    backup_policy_name: str | None = None
    health_endpoint: str | None = None
    rpo_seconds: int | None = Field(default=None, gt=0)
    rto_seconds: int | None = Field(default=None, gt=0)
    notes: str = ""


class ActorRequest(BaseModel):
    actor: str = "system"
    trigger: str = "manual"


def create_dr_app(service: DisasterRecoveryService) -> FastAPI:
    app = FastAPI(
        title="apexquant-disaster-recovery",
        version="0.25.0",
    )

    app.state.service = service

    @app.exception_handler(DRNotFoundError)
    async def not_found_handler(request, exc: DRNotFoundError):
        return JSONResponse(status_code=404, content={"error": str(exc)})

    @app.exception_handler(DisasterRecoveryError)
    async def dr_error_handler(request, exc: DisasterRecoveryError):
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, bool]:
        return {"ready": True}

    @app.post("/v1/dr/plans", status_code=201)
    def create_plan(payload: PlanCreateRequest):
        plan = RecoveryPlan(
            name=payload.name,
            environment=payload.environment,
            description=payload.description,
            criticality_tier=payload.criticality_tier,
            rpo_seconds=payload.rpo_seconds,
            rto_seconds=payload.rto_seconds,
            drill_max_age_days=payload.drill_max_age_days,
            status=PlanStatus.DRAFT,
        )

        return service.create_plan(plan)

    @app.get("/v1/dr/plans")
    def list_plans():
        return service._repository.list_plans()

    @app.get("/v1/dr/plans/{plan_id}")
    def get_plan(plan_id: UUID):
        plan = service._repository.get_plan(plan_id)

        if plan is None:
            raise DRNotFoundError(f"plan not found: {plan_id}")

        return plan

    @app.post("/v1/dr/plans/{plan_id}/activate")
    def activate_plan(plan_id: UUID, payload: ActorRequest):
        return service.activate_plan(plan_id, actor=payload.actor)

    @app.post("/v1/dr/plans/{plan_id}/components", status_code=201)
    def add_component(plan_id: UUID, payload: ComponentCreateRequest):
        component = RecoveryComponent(
            component_name=payload.component_name,
            component_type=payload.component_type,
            recovery_strategy=payload.recovery_strategy,
            priority=payload.priority,
            backup_policy_name=payload.backup_policy_name,
            health_endpoint=payload.health_endpoint,
            rpo_seconds=payload.rpo_seconds,
            rto_seconds=payload.rto_seconds,
            notes=payload.notes,
        )

        return service.add_component(plan_id, component)

    @app.get("/v1/dr/plans/{plan_id}/components")
    def list_components(plan_id: UUID):
        return service._repository.list_components(plan_id)

    @app.post("/v1/dr/plans/{plan_id}/drills", status_code=201)
    def run_drill(plan_id: UUID, payload: ActorRequest):
        return service.run_drill(
            plan_id,
            actor=payload.actor,
            trigger=payload.trigger,
        )

    @app.get("/v1/dr/plans/{plan_id}/readiness")
    def readiness(plan_id: UUID):
        return service.readiness(plan_id)

    @app.get("/v1/dr/drills")
    def list_drills(plan_id: UUID | None = None, limit: int = 100):
        return service._repository.list_drills(plan_id=plan_id, limit=limit)

    @app.get("/v1/dr/drills/{drill_id}")
    def get_drill(drill_id: UUID):
        drill = service._repository.get_drill(drill_id)

        if drill is None:
            raise DRNotFoundError(f"drill not found: {drill_id}")

        return drill

    @app.get("/v1/dr/status")
    def status():
        return service.status()

    return app