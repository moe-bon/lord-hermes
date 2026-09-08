from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    generate_latest,
)
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from apexquant_logging.core.clickhouse import insert_logs_into_clickhouse
from apexquant_logging.core.repository import (
    LoggingConfigRepository,
    apply_migrations,
)
from apexquant_logging.core.settings import LoggingCoreSettings
from apexquant_logging.models import LogEnvelope
from apexquant_logging.redaction import redact_data


class LogsIngestRequest(BaseModel):
    logs: list[LogEnvelope] = Field(default_factory=list)


class ServiceLogConfigRequest(BaseModel):
    service_name: str
    environment: str
    plane: str
    default_level: str = "INFO"
    json_output: bool = True
    redaction_enabled: bool = True


def serialize_log(log: LogEnvelope) -> str:
    payload = log.model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=True, default=str)


def append_file_lines(path: str, lines: list[str]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line + "\n")


def create_logging_core_app(settings: LoggingCoreSettings) -> FastAPI:
    registry = CollectorRegistry()

    logs_ingested_total = Counter(
        "apex_logs_ingested_total",
        "Structured logs ingested",
        registry=registry,
    )

    log_sink_failures_total = Counter(
        "apex_log_sink_failures_total",
        "Structured log sink failures",
        labelnames=("sink",),
        registry=registry,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        pool: ConnectionPool | None = None

        if settings.database_url:
            apply_migrations(settings.database_url, settings.migrations_dir)

            pool = ConnectionPool(
                conninfo=settings.database_url,
                max_size=5,
            )

        app.state.pool = pool
        app.state.repository = LoggingConfigRepository(pool) if pool else None

        try:
            yield
        finally:
            if pool is not None:
                pool.close()

    app = FastAPI(
        title="apexquant-logging-core",
        version="0.14.0",
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.metrics_registry = registry
    app.state.logs_ingested_total = logs_ingested_total
    app.state.log_sink_failures_total = log_sink_failures_total

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz(request: Request) -> JSONResponse:
        if settings.database_url and request.app.state.pool is None:
            return JSONResponse(status_code=503, content={"ready": False})

        return JSONResponse({"ready": True})

    @app.get("/metrics")
    async def metrics(request: Request):
        return generate_latest(request.app.state.metrics_registry)

    @app.post("/v1/logs")
    async def ingest_logs(payload: LogsIngestRequest, request: Request) -> dict:
        if len(payload.logs) > settings.max_batch_size:
            raise HTTPException(
                status_code=400,
                detail=f"batch size exceeds maximum of {settings.max_batch_size}",
            )

        redacted_logs: list[LogEnvelope] = []

        for log in payload.logs:
            redacted = log.model_copy(update={"data": redact_data(log.data)})
            redacted_logs.append(redacted)

        lines = [serialize_log(log) for log in redacted_logs]

        sink_successes: list[bool] = []

        if settings.stdout_enabled:
            for line in lines:
                print(line, flush=True)

            sink_successes.append(True)

        if settings.file_sink_path:
            try:
                await asyncio.to_thread(
                    append_file_lines,
                    settings.file_sink_path,
                    lines,
                )
                sink_successes.append(True)
            except Exception:
                request.app.state.log_sink_failures_total.labels("file").inc()
                sink_successes.append(False)

        if settings.clickhouse_url:
            try:
                await insert_logs_into_clickhouse(
                    settings.clickhouse_url,
                    settings.clickhouse_database,
                    redacted_logs,
                )
                sink_successes.append(True)
            except Exception:
                request.app.state.log_sink_failures_total.labels("clickhouse").inc()
                sink_successes.append(False)

        request.app.state.logs_ingested_total.inc(len(redacted_logs))

        if settings.strict_mode and sink_successes and not any(sink_successes):
            raise HTTPException(
                status_code=503,
                detail="all log sinks failed",
            )

        return {
            "accepted": len(redacted_logs),
            "sinks": {
                "stdout_enabled": settings.stdout_enabled,
                "file_sink_enabled": bool(settings.file_sink_path),
                "clickhouse_enabled": bool(settings.clickhouse_url),
            },
        }

    @app.get("/v1/logging/configs")
    async def get_service_configs(request: Request):
        repository = request.app.state.repository

        if repository is None:
            return {"configs": []}

        configs = await asyncio.to_thread(repository.get_service_configs)

        return {"configs": configs}

    @app.put("/v1/logging/configs")
    async def upsert_service_config(
        payload: ServiceLogConfigRequest,
        request: Request,
    ):
        repository = request.app.state.repository

        if repository is None:
            raise HTTPException(
                status_code=503,
                detail="logging configuration database is not configured",
            )

        await asyncio.to_thread(
            repository.upsert_service_config,
            payload.service_name,
            payload.environment,
            payload.plane,
            payload.default_level,
            payload.json_output,
            payload.redaction_enabled,
        )

        return {"status": "saved"}

    return app