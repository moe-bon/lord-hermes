from __future__ import annotations

from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from apexquant_backup_recovery.errors import BackupError, BackupNotFoundError
from apexquant_backup_recovery.models import BackupPolicy, TargetSystem
from apexquant_backup_recovery.service import BackupService
from apexquant_backup_recovery.settings import BackupSettings


class PolicyCreateRequest(BaseModel):
    name: str
    target_system: TargetSystem = TargetSystem.POSTGRES
    target_name: str
    target_connection_ref: str = Field(pattern=r"^(env://|vault://|secret://).+")
    storage_bucket: str | None = None
    storage_prefix: str = "backups/"
    interval_minutes: int = Field(default=1440, gt=0)
    backup_timeout_seconds: int = Field(default=3600, gt=0)
    retention_count: int | None = Field(default=None, gt=0)
    retention_days: int | None = Field(default=None, gt=0)
    delete_expired: bool = False
    encryption_key_ref: str | None = None
    enabled: bool = True


class RestoreRequest(BaseModel):
    target_connection_ref: str = Field(pattern=r"^(env://|vault://|secret://).+")
    dry_run: bool = True
    confirm: bool = False
    allow_production_restore: bool = False


def create_backup_app(
    service: BackupService,
    settings: BackupSettings,
) -> FastAPI:
    app = FastAPI(
        title="apexquant-backup-recovery",
        version="0.24.0",
    )

    app.state.service = service
    app.state.settings = settings

    @app.exception_handler(BackupNotFoundError)
    async def backup_not_found_handler(request: Request, exc: BackupNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"error": str(exc)},
        )

    @app.exception_handler(BackupError)
    async def backup_error_handler(request: Request, exc: BackupError):
        return JSONResponse(
            status_code=400,
            content={"error": str(exc)},
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, bool]:
        return {"ready": True}

    @app.post("/v1/backup/policies", status_code=201)
    def create_policy(payload: PolicyCreateRequest):
        policy = BackupPolicy(
            name=payload.name,
            target_system=payload.target_system,
            target_name=payload.target_name,
            target_connection_ref=payload.target_connection_ref,
            storage_bucket=payload.storage_bucket or settings.default_bucket,
            storage_prefix=payload.storage_prefix,
            interval_minutes=payload.interval_minutes,
            backup_timeout_seconds=payload.backup_timeout_seconds,
            retention_count=payload.retention_count,
            retention_days=payload.retention_days,
            delete_expired=payload.delete_expired,
            encryption_key_ref=payload.encryption_key_ref,
            enabled=payload.enabled,
        )

        return service.create_policy(policy)

    @app.get("/v1/backup/policies")
    def list_policies():
        return service.list_policies()

    @app.post("/v1/backup/policies/{policy_id}/run")
    def run_policy(policy_id: UUID, trigger: str = "manual"):
        return service.create_backup(policy_id, trigger=trigger)

    @app.post("/v1/backup/policies/{policy_id}/retention")
    def apply_retention(policy_id: UUID):
        return service.apply_retention(policy_id)

    @app.post("/v1/backup/run-due")
    def run_due():
        return service.run_due()

    @app.get("/v1/backup/runs")
    def list_runs(policy_id: UUID | None = None, limit: int = 100):
        return service._repository.list_runs(policy_id=policy_id, limit=limit)

    @app.get("/v1/backup/runs/{run_id}")
    def get_run(run_id: UUID):
        run = service._repository.get_run(run_id)

        if run is None:
            raise BackupNotFoundError(f"backup run not found: {run_id}")

        return run

    @app.post("/v1/backup/runs/{run_id}/verify")
    def verify_backup(run_id: UUID):
        return service.verify_backup(run_id)

    @app.post("/v1/backup/runs/{run_id}/restore")
    def restore_backup(run_id: UUID, payload: RestoreRequest):
        return service.restore_backup(
            run_id=run_id,
            target_connection_ref=payload.target_connection_ref,
            dry_run=payload.dry_run,
            confirm=payload.confirm,
            allow_production_restore=payload.allow_production_restore,
        )

    return app