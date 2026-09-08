from __future__ import annotations

import asyncio
import time
from typing import Protocol

from apexquant_health.models import DependencyStatus, HealthStatus


class DependencyCheck(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def type(self) -> str: ...

    async def check(self) -> DependencyStatus: ...


async def run_with_timeout(coro, timeout_seconds: float = 2.0) -> DependencyStatus:
    start = time.perf_counter()
    try:
        result = await asyncio.wait_for(coro, timeout=timeout_seconds)
        latency = (time.perf_counter() - start) * 1000
        return DependencyStatus(
            status=HealthStatus.HEALTHY,
            latency_ms=round(latency, 3),
        )
    except asyncio.TimeoutError:
        return DependencyStatus(
            status=HealthStatus.UNHEALTHY,
            error=f"timeout after {timeout_seconds}s",
        )
    except Exception as exc:
        return DependencyStatus(
            status=HealthStatus.UNHEALTHY,
            error=str(exc),
        )