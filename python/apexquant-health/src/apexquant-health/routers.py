from __future__ import annotations

from fastapi import APIRouter, Response, status

from apexquant_health.checker import HealthChecker
from apexquant_health.models import HealthStatus


def create_health_router(checker: HealthChecker) -> APIRouter:
    router = APIRouter()

    @router.get("/livez")
    async def livez() -> dict[str, str]:
        return {"status": "alive"}

    @router.get("/readyz")
    async def readyz(response: Response) -> dict[str, str]:
        is_ready = await checker.check_ready()
        if not is_ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "not_ready"}
        return {"status": "ready"}

    @router.get("/healthz")
    async def healthz(response: Response):
        health = await checker.check_health()
        if health.status == HealthStatus.UNHEALTHY:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return health.model_dump(mode="json")

    return router