from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    generate_latest,
)
from psycopg_pool import ConnectionPool
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from apexquant_config_validation.repository import (
    ConfigRepository,
    apply_migrations,
)
from apexquant_config_validation.schemas import SCHEMA_FILES
from apexquant_config_validation.validator import ConfigValidator


class ConfigValidationSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APEX_CONFIG_VALIDATION_",
        env_file=".env",
        extra="ignore",
    )

    http_addr: str = "0.0.0.0:8092"
    environment: str = "local"
    database_url: str | None = None
    migrations_dir: str = "/migrations/postgres/config_validation"
    migrate_on_start: bool = True


class ValidateRequest(BaseModel):
    schema_key: str
    document: dict[str, Any]
    persist: bool = False
    actor: str = "system"


def create_config_validation_app(
    settings: ConfigValidationSettings,
) -> FastAPI:
    registry = CollectorRegistry()

    validations_total = Counter(
        "apex_config_validations_total",
        "Configuration validations",
        labelnames=("schema_key", "result"),
        registry=registry,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        pool: ConnectionPool | None = None
        repository: ConfigRepository | None = None

        if settings.database_url:
            if settings.migrate_on_start:
                apply_migrations(settings.database_url, settings.migrations_dir)

            pool = ConnectionPool(
                conninfo=settings.database_url,
                max_size=10,
            )

            repository = ConfigRepository(pool)

        app.state.pool = pool
        app.state.repository = repository
        app.state.validator = ConfigValidator()

        try:
            yield
        finally:
            if pool is not None:
                pool.close()

    app = FastAPI(
        title="apexquant-config-validation",
        version="0.23.0",
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.metrics_registry = registry

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz(request: Request) -> JSONResponse:
        if settings.database_url:
            try:
                with request.app.state.pool.connection() as conn:
                    conn.execute("SELECT 1")
            except Exception:
                return JSONResponse(status_code=503, content={"ready": False})

        return JSONResponse({"ready": True})

    @app.get("/metrics")
    def metrics(request: Request):
        return generate_latest(request.app.state.metrics_registry)

    @app.get("/v1/config/schemas")
    def list_schemas() -> dict[str, Any]:
        return {"schemas": sorted(SCHEMA_FILES.keys())}

    @app.post("/v1/config/validate")
    def validate_config(payload: ValidateRequest, request: Request):
        validator: ConfigValidator = request.app.state.validator
        repository: ConfigRepository | None = request.app.state.repository

        report = validator.validate(payload.schema_key, payload.document)

        validations_total.labels(
            payload.schema_key,
            "pass" if report.ok else "fail",
        ).inc()

        if not report.ok:
            return JSONResponse(
                status_code=422,
                content=report.model_dump(mode="json"),
            )

        document_id = None

        if payload.persist:
            if repository is None:
                raise HTTPException(
                    status_code=503,
                    detail="configuration database is not configured",
                )

            service_name = payload.document.get("service_name")
            environment = payload.document.get("environment")

            schema_version = (
                payload.schema_key.split("/", 1)[1]
                if "/" in payload.schema_key
                else "v1"
            )

            document_id = repository.persist_document(
                schema_key=payload.schema_key,
                schema_version=schema_version,
                service_name=service_name,
                environment=environment,
                config_hash=report.config_hash or "",
                values=payload.document,
                created_by=payload.actor,
            )

            repository.persist_validation_run(
                document_id=document_id,
                schema_key=payload.schema_key,
                environment=environment,
                trigger="api",
                ok=report.ok,
                errors=[issue.model_dump(mode="json") for issue in report.errors],
                warnings=[issue.model_dump(mode="json") for issue in report.warnings],
                config_hash=report.config_hash,
            )

            repository.record_event(
                document_id=document_id,
                event_type="CONFIG_VALIDATED",
                actor=payload.actor,
                reason="configuration validated",
                before_hash=None,
                after_hash=report.config_hash,
            )

        body = report.model_dump(mode="json")
        body["document_id"] = document_id

        return body

    return app