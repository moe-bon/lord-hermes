from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable
from uuid import uuid4

from apexquant_logging.context import set_context

logger = logging.getLogger("apex.http")


async def request_logging_middleware(request, call_next: Callable[[object], Awaitable]):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    trace_id = request.headers.get("x-trace-id")
    correlation_id = request.headers.get("x-correlation-id")
    actor_id = request.headers.get("x-actor-id")

    set_context(
        request_id=request_id,
        trace_id=trace_id,
        correlation_id=correlation_id,
        actor_id=actor_id,
    )

    started_at = time.perf_counter()

    response = await call_next(request)

    duration_ms = (time.perf_counter() - started_at) * 1000

    response.headers["x-request-id"] = request_id

    logger.info(
        "http_request",
        extra={
            "data": {
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 3),
            }
        },
    )

    return response