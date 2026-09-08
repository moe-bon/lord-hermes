from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest

from apexquant_service_framework.logging import configure_logging
from apexquant_service_framework.metrics import ServiceMetrics
from apexquant_service_framework.registration import (
    RegistrationClient,
    RegistrationState,
)
from apexquant_service_framework.service_contract import ServiceDescriptor
from apexquant_service_framework.settings import ServiceFrameworkSettings


class RuntimeState:
    def __init__(self) -> None:
        self.registered: bool = False
        self.ready: bool = True
        self.registration_error: str | None = None
        self.heartbeat_task: asyncio.Task[None] | None = None


def create_service_app(
    settings: ServiceFrameworkSettings,
    descriptor: ServiceDescriptor,
    *,
    extra_router: APIRouter | None = None,
) -> FastAPI:
    configure_logging(settings.service_name)

    registry = CollectorRegistry()
    metrics = ServiceMetrics(registry, settings.service_name)
    metrics.set_info(settings.environment, settings.plane.value)

    runtime = RuntimeState()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client: RegistrationClient | None = None

        if settings.registration_url:
            client = RegistrationClient(settings.registration_url)

            try:
                await client.register(descriptor)
                runtime.registered = True
                runtime.ready = True
                runtime.heartbeat_task = asyncio.create_task(
                    _heartbeat_loop(
                        client=client,
                        service_id=descriptor.service_id or "",
                        interval_seconds=settings.heartbeat_interval_seconds,
                        runtime=runtime,
                    )
                )
            except Exception as exc:
                runtime.registration_error = str(exc)
                runtime.ready = False

                if settings.registration_required:
                    await client.aclose()
                    raise

        try:
            yield
        finally:
            if runtime.heartbeat_task is not None:
                runtime.heartbeat_task.cancel()
                try:
                    await runtime.heartbeat_task
                except asyncio.CancelledError:
                    pass

            if client is not None:
                await client.aclose()

    app = FastAPI(
        title=settings.service_name,
        version=settings.service_version,
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.descriptor = descriptor
    app.state.metrics = metrics
    app.state.runtime = runtime

    @app.middleware("http")
    async def request_metrics_middleware(request, call_next):
        response = await call_next(request)

        metrics.requests_total.labels(
            request.method,
            request.url.path,
            str(response.status_code),
        ).inc()

        return response

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        ready = runtime.ready

        if settings.registration_required and settings.registration_url:
            ready = ready and runtime.registered

        metrics.ready.set(1 if ready else 0)

        if ready:
            return JSONResponse({"ready": True})

        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "registration_error": runtime.registration_error,
            },
        )

    @app.get("/metrics")
    async def metrics_endpoint() -> Response:
        payload = generate_latest(registry)
        return Response(content=payload, media_type=CONTENT_TYPE_LATEST)

    if extra_router is not None:
        app.include_router(extra_router)

    return app


async def _heartbeat_loop(
    *,
    client: RegistrationClient,
    service_id: str,
    interval_seconds: float,
    runtime: RuntimeState,
) -> None:
    while True:
        await asyncio.sleep(interval_seconds)

        try:
            await client.heartbeat(
                service_id=service_id,
                state=RegistrationState.READY,
                detail="python service heartbeat",
            )
            runtime.ready = True
        except Exception:
            runtime.ready = False