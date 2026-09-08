from __future__ import annotations

import time
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from apexquant_metrics.registry import ApexMetricRegistry


class MetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, registry: ApexMetricRegistry) -> None:
        super().__init__(app)

        self._requests_total = registry.counter(
            name="apexquant_http_requests_total",
            description="Total HTTP requests",
            labels=("method", "path", "status"),
        )

        self._request_duration = registry.histogram(
            name="apexquant_http_request_duration_seconds",
            description="HTTP request duration in seconds",
            labels=("method", "path"),
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        )

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        method = request.method
        path = request.url.path

        # Normalize path to prevent cardinality explosion from path parameters
        if path.startswith("/api/") and len(path.split("/")) > 4:
            path = "/api/{service}/{version}"

        started_at = time.perf_counter()

        try:
            response = await call_next(request)
            status = str(response.status_code)
        except Exception:
            status = "500"
            raise
        finally:
            duration = time.perf_counter() - started_at

            self._requests_total.labels(
                method=method,
                path=path,
                status=status,
            ).inc()

            self._request_duration.labels(
                method=method,
                path=path,
            ).observe(duration)

        return response