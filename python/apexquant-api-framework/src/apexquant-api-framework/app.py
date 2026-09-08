from __future__ import annotations

import uuid
from typing import Awaitable, Callable

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    generate_latest,
)
from starlette.exceptions import HTTPException as StarletteHTTPException

from apexquant_api_framework.models import ApiInfo


def create_api_app(
    *,
    service_name: str,
    service_version: str,
    environment: str,
    plane: str,
    description: str = "",
    extra_router: APIRouter | None = None,
) -> FastAPI:
    registry = CollectorRegistry()

    requests_total = Counter(
        "apex_api_requests_total",
        "API requests",
        labelnames=("method", "path", "status"),
        registry=registry,
    )

    app = FastAPI(
        title=service_name,
        version=service_version,
        description=description,
    )

    app.state.service_name = service_name
    app.state.service_version = service_version
    app.state.environment = environment
    app.state.plane = plane
    app.state.metrics_registry = registry
    app.state.requests_total = requests_total

    @app.middleware("http")
    async def api_context_middleware(request: Request, call_next: Callable[[Request], Awaitable]) -> JSONResponse:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)

        response.headers["x-request-id"] = request_id
        response.headers["x-apex-service"] = service_name
        response.headers["x-apex-plane"] = plane
        response.headers["x-apex-environment"] = environment
        response.headers["x-apex-version"] = service_version

        requests_total.labels(
            request.method,
            request.url.path,
            str(response.status_code),
        ).inc()

        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "HTTP_ERROR",
                    "message": str(exc.detail),
                }
            },
            headers={"x-request-id": getattr(request.state, "request_id", "")},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "request validation failed",
                }
            },
            headers={"x-request-id": getattr(request.state, "request_id", "")},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "internal server error",
                }
            },
            headers={"x-request-id": getattr(request.state, "request_id", "")},
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> dict[str, bool]:
        return {"ready": True}

    @app.get("/metrics")
    async def metrics() -> bytes:
        return generate_latest(registry)

    @app.get("/v1/api/info")
    async def api_info() -> ApiInfo:
        return ApiInfo(
            service_name=service_name,
            service_version=service_version,
            environment=environment,
            plane=plane,
            description=description,
        )

    if extra_router is not None:
        app.include_router(extra_router)

    return app