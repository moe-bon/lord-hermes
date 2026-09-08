from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    generate_latest,
)
from psycopg_pool import ConnectionPool

from apexquant_auth.models import (
    AuthorizeRequest,
    AuthorizeResponse,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    IssueTokenRequest,
    IssueTokenResponse,
)
from apexquant_auth.repository import PostgresAuthRepository
from apexquant_auth.security import AuthSecurityError, decode_token_secret
from apexquant_auth.service import AuthService


class AuthApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


def create_auth_app(
    database_url: str,
    token_secret_b64: str,
    bootstrap_subject: str,
    bootstrap_api_key: str,
    bootstrap_permissions: list[str],
    migrations_dir: str,
    migrate_on_start: bool = True,
) -> FastAPI:
    registry = CollectorRegistry()

    auth_requests_total = Counter(
        "apex_auth_requests_total",
        "Authentication service requests",
        labelnames=("endpoint", "decision"),
        registry=registry,
    )

    token_secret = decode_token_secret(token_secret_b64)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if migrate_on_start:
            from apexquant_auth.migrations import apply_migrations

            apply_migrations(database_url, migrations_dir)

        pool = ConnectionPool(
            conninfo=database_url,
            max_size=10,
            kwargs={"autocommit": True},
        )

        repository = PostgresAuthRepository(pool)
        service = AuthService(repository=repository, token_secret=token_secret)

        service.ensure_bootstrap(
            subject_name=bootstrap_subject,
            api_key=bootstrap_api_key,
            permissions=bootstrap_permissions,
        )

        app.state.pool = pool
        app.state.repository = repository
        app.state.service = service

        try:
            yield
        finally:
            pool.close()

    app = FastAPI(
        title="apexquant-auth",
        version="0.11.0",
        lifespan=lifespan,
    )

    app.state.metrics_registry = registry
    app.state.auth_requests_total = auth_requests_total

    @app.exception_handler(AuthApiError)
    async def auth_api_error_handler(request: Request, exc: AuthApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                }
            },
        )

    def get_service(request: Request) -> AuthService:
        return request.app.state.service

    def get_auth_context(
        request: Request,
        authorization: str | None = Header(default=None),
    ):
        service: AuthService = get_service(request)

        if not authorization or not authorization.startswith("Bearer "):
            raise AuthApiError(401, "UNAUTHORIZED", "missing bearer token")

        token = authorization.removeprefix("Bearer ").strip()

        try:
            return service.verify_token(token)
        except AuthSecurityError as exc:
            raise AuthApiError(401, "UNAUTHORIZED", str(exc))

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz(request: Request) -> JSONResponse:
        try:
            with request.app.state.pool.connection() as conn:
                conn.execute("SELECT 1")

            return JSONResponse({"ready": True})
        except Exception:
            return JSONResponse(status_code=503, content={"ready": False})

    @app.get("/metrics")
    async def metrics(request: Request):
        return generate_latest(request.app.state.metrics_registry)

    @app.post("/v1/auth/tokens", response_model=IssueTokenResponse)
    async def issue_token(
        payload: IssueTokenRequest,
        request: Request,
    ) -> IssueTokenResponse:
        service: AuthService = get_service(request)

        try:
            response = service.issue_token(payload.api_key, payload.ttl_seconds)
        except AuthSecurityError as exc:
            request.app.state.auth_requests_total.labels("/v1/auth/tokens", "DENY").inc()
            raise AuthApiError(401, "INVALID_CREDENTIAL", str(exc))

        request.app.state.auth_requests_total.labels("/v1/auth/tokens", "ALLOW").inc()
        return response

    @app.get("/v1/auth/verify")
    async def verify_token(context=Depends(get_auth_context)):
        return context

    @app.post("/v1/auth/authorize", response_model=AuthorizeResponse)
    async def authorize(
        payload: AuthorizeRequest,
        request: Request,
        context=Depends(get_auth_context),
    ) -> AuthorizeResponse:
        service: AuthService = get_service(request)

        allowed = service.authorize(context, payload.action, payload.resource)

        request.app.state.auth_requests_total.labels(
            "/v1/auth/authorize",
            "ALLOW" if allowed else "DENY",
        ).inc()

        return AuthorizeResponse(
            allowed=allowed,
            reason=f"{payload.action}:{payload.resource}",
        )

    @app.post("/v1/auth/api-keys", response_model=CreateApiKeyResponse)
    async def create_api_key(
        payload: CreateApiKeyRequest,
        request: Request,
        context=Depends(get_auth_context),
    ) -> CreateApiKeyResponse:
        service: AuthService = get_service(request)

        try:
            return service.create_api_key(context, payload)
        except AuthSecurityError as exc:
            raise AuthApiError(403, "FORBIDDEN", str(exc))

    @app.post("/v1/auth/api-keys/revoke")
    async def revoke_api_key(
        payload: dict,
        request: Request,
        context=Depends(get_auth_context),
    ) -> dict[str, bool]:
        service: AuthService = get_service(request)

        identifier = str(payload.get("identifier", "")).strip()

        if not identifier:
            raise AuthApiError(400, "INVALID_REQUEST", "identifier is required")

        try:
            revoked = service.revoke_api_key(context, identifier)
        except AuthSecurityError as exc:
            raise AuthApiError(403, "FORBIDDEN", str(exc))

        return {"revoked": revoked}

    return app