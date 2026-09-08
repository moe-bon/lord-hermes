from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    generate_latest,
)
from psycopg_pool import ConnectionPool

from apexquant_service_versioning.errors import VersioningError
from apexquant_service_versioning.models import (
    ActorRequest,
    ReleaseRequest,
    ServiceCreate,
    VersionCreate,
)
from apexquant_service_versioning.repository import (
    InMemoryRepository,
    PostgresRepository,
    apply_migrations,
)
from apexquant_service_versioning.service import VersioningService
from apexquant_service_versioning.settings import ServiceVersioningSettings


def create_service_versioning_app(
    settings: ServiceVersioningSettings,
) -> FastAPI:
    registry = CollectorRegistry()

    requests_total = Counter(
        "apex_service_versioning_requests_total",
        "Service versioning API requests",
        labelnames=("method", "path", "status"),
        registry=registry,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        pool: ConnectionPool | None = None
        repository = InMemoryRepository()

        if settings.database_url:
            if settings.migrate_on_start:
                apply_migrations(settings.database_url, settings.migrations_dir)

            pool = ConnectionPool(
                conninfo=settings.database_url,
                max_size=10,
            )

            repository = PostgresRepository(pool)

        app.state.repository = repository
        app.state.versioning_service = VersioningService(repository)

        try:
            yield
        finally:
            if pool is not None:
                pool.close()

    app = FastAPI(
        title="apexquant-service-versioning",
        version="0.21.0",
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.metrics_registry = registry

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        response = await call_next(request)

        requests_total.labels(
            request.method,
            request.url.path,
            str(response.status_code),
        ).inc()

        return response

    @app.exception_handler(VersioningError)
    async def versioning_error_handler(
        request: Request,
        exc: VersioningError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                }
            },
        )

    def get_service(request: Request) -> VersioningService:
        return request.app.state.versioning_service

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz(request: Request) -> JSONResponse:
        if settings.database_url:
            try:
                with request.app.state.repository._pool.connection() as conn:
                    conn.execute("SELECT 1")
            except Exception:
                return JSONResponse(status_code=503, content={"ready": False})

        return JSONResponse({"ready": True})

    @app.get("/metrics")
    def metrics(request: Request):
        return generate_latest(request.app.state.metrics_registry)

    @app.post("/v1/services", status_code=201)
    def register_service(payload: ServiceCreate, request: Request):
        service = get_service(request)
        return service.register_service(payload)

    @app.get("/v1/services")
    def list_services(request: Request):
        service = get_service(request)
        return service.list_services()

    @app.post("/v1/services/{service_name}/versions", status_code=201)
    def create_version(
        service_name: str,
        payload: VersionCreate,
        request: Request,
    ):
        service = get_service(request)
        return service.create_version(service_name, payload)

    @app.get("/v1/services/{service_name}/versions")
    def list_versions(service_name: str, request: Request):
        service = get_service(request)
        return service.list_versions(service_name)

    @app.get("/v1/services/{service_name}/versions/{version}")
    def get_version(service_name: str, version: str, request: Request):
        service = get_service(request)
        return service.get_version(service_name, version)

    @app.post("/v1/services/{service_name}/versions/{version}/release")
    def release_version(
        service_name: str,
        version: str,
        payload: ReleaseRequest,
        request: Request,
    ):
        service = get_service(request)

        return service.release_version(
            service_name=service_name,
            version=version,
            git_sha=payload.git_sha,
            image_tag=payload.image_tag,
            checksum_sha256=payload.checksum_sha256,
            actor=payload.actor,
            reason=payload.reason,
        )

    @app.post("/v1/services/{service_name}/versions/{version}/deprecate")
    def deprecate_version(
        service_name: str,
        version: str,
        payload: ActorRequest,
        request: Request,
    ):
        service = get_service(request)

        return service.deprecate_version(
            service_name=service_name,
            version=version,
            actor=payload.actor,
            reason=payload.reason,
        )

    @app.post("/v1/services/{service_name}/versions/{version}/retire")
    def retire_version(
        service_name: str,
        version: str,
        payload: ActorRequest,
        request: Request,
    ):
        service = get_service(request)

        return service.retire_version(
            service_name=service_name,
            version=version,
            actor=payload.actor,
            reason=payload.reason,
        )

    @app.get("/v1/services/{service_name}/versions/{version}/compatibility")
    def check_compatibility(
        service_name: str,
        version: str,
        request: Request,
    ):
        service = get_service(request)
        return service.check_compatibility(service_name, version)

    return app