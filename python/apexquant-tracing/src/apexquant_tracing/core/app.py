from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from opentelemetry import trace
from opentelemetry.propagate import extract
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    generate_latest,
)
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from apexquant_tracing.context import TraceContext, parse_traceparent
from apexquant_tracing.core.repository import (
    TracingConfigRepository,
    apply_migrations,
)
from apexquant_tracing.core.settings import TracingCoreSettings
from apexquant_tracing.otel import configure_tracing, shutdown_tracing


class VerifyContextRequest(BaseModel):
    traceparent: str


class TestSpanRequest(BaseModel):
    name: str = "apex.tracing.test"
    traceparent: str | None = None


class ServiceTracingConfigRequest(BaseModel):
    service_name: str
    environment: str
    plane: str
    otlp_endpoint: str | None = None
    tempo_query_endpoint: str | None = None
    sample_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    tracing_enabled: bool = True
    redaction_enabled: bool = True


def create_tracing_core_app(settings: TracingCoreSettings) -> FastAPI:
    registry = CollectorRegistry()

    context_verifications_total = Counter(
        "apex_trace_context_verifications_total",
        "Trace context verifications",
        registry=registry,
    )

    test_spans_created_total = Counter(
        "apex_test_spans_created_total",
        "Test spans created",
        registry=registry,
    )

    pipeline_verifications_total = Counter(
        "apex_tracing_pipeline_verifications_total",
        "Tracing pipeline verifications",
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

        provider = configure_tracing(
            service_name=settings.service_name,
            environment=settings.environment,
            plane=settings.plane,
            service_version=settings.service_version,
            otlp_endpoint=settings.otlp_endpoint,
            sample_ratio=settings.sample_ratio,
        )

        app.state.pool = pool
        app.state.repository = TracingConfigRepository(pool) if pool else None
        app.state.tracer_provider = provider
        app.state.tracer = trace.get_tracer(settings.service_name)

        try:
            yield
        finally:
            shutdown_tracing(provider)

            if pool is not None:
                pool.close()

    app = FastAPI(
        title="apexquant-tracing-core",
        version="0.16.0",
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.metrics_registry = registry
    app.state.context_verifications_total = context_verifications_total
    app.state.test_spans_created_total = test_spans_created_total
    app.state.pipeline_verifications_total = pipeline_verifications_total

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

    @app.post("/v1/tracing/context/verify")
    async def verify_context(
        payload: VerifyContextRequest,
        request: Request,
    ) -> dict:
        request.app.state.context_verifications_total.inc()

        context = parse_traceparent(payload.traceparent)

        if context is None:
            return {
                "valid": False,
                "trace_id": None,
                "span_id": None,
                "sampled": False,
            }

        return {
            "valid": True,
            "trace_id": context.trace_id,
            "span_id": context.span_id,
            "sampled": context.sampled,
        }

    @app.post("/v1/tracing/test-span")
    async def create_test_span(
        payload: TestSpanRequest,
        request: Request,
    ) -> dict:
        tracer = request.app.state.tracer

        carrier = {}

        if payload.traceparent:
            carrier["traceparent"] = payload.traceparent

        parent_context = extract(carrier)

        with tracer.start_as_current_span(
            payload.name,
            context=parent_context,
        ) as span:
            span_context = span.get_span_context()

            trace_id = format(span_context.trace_id, "032x")
            span_id = format(span_context.span_id, "016x")

        provider = request.app.state.tracer_provider

        exported = False

        if settings.otlp_endpoint and hasattr(provider, "force_flush"):
            try:
                provider.force_flush()
                exported = True
            except Exception:
                exported = False

        request.app.state.test_spans_created_total.inc()

        return {
            "trace_id": trace_id,
            "span_id": span_id,
            "exported": exported,
        }

    @app.get("/v1/tracing/verify")
    async def verify_pipeline(request: Request) -> dict:
        request.app.state.pipeline_verifications_total.inc()

        tempo_ready = False

        if settings.tempo_query_endpoint:
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    response = await client.get(
                        f"{settings.tempo_query_endpoint.rstrip('/')}/ready"
                    )
                    tempo_ready = response.status_code == 200
            except Exception:
                tempo_ready = False

        span_response = await create_test_span(
            TestSpanRequest(name="apex.tracing.pipeline-verification"),
            request,
        )

        ok = tempo_ready and bool(span_response.get("trace_id"))

        return {
            "ok": ok,
            "tempo_ready": tempo_ready,
            "trace_id": span_response.get("trace_id"),
            "span_id": span_response.get("span_id"),
            "exported": span_response.get("exported"),
        }

    @app.get("/v1/tracing/configs/{service_name}")
    async def get_service_tracing_config(
        service_name: str,
        request: Request,
    ):
        repository = request.app.state.repository

        if repository is None:
            raise HTTPException(
                status_code=503,
                detail="tracing configuration database is not configured",
            )

        config = await asyncio.to_thread(repository.get_config, service_name)

        if config is None:
            raise HTTPException(status_code=404, detail="service config not found")

        return config

    @app.put("/v1/tracing/configs")
    async def upsert_service_tracing_config(
        payload: ServiceTracingConfigRequest,
        request: Request,
    ):
        repository = request.app.state.repository

        if repository is None:
            raise HTTPException(
                status_code=503,
                detail="tracing configuration database is not configured",
            )

        await asyncio.to_thread(
            repository.upsert_config,
            payload.service_name,
            payload.environment,
            payload.plane,
            payload.otlp_endpoint,
            payload.tempo_query_endpoint,
            payload.sample_ratio,
            payload.tracing_enabled,
            payload.redaction_enabled,
        )

        return {"status": "saved"}

    return app