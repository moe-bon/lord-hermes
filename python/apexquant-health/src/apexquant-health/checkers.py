from __future__ import annotations

from apexquant_health.checks import DependencyCheck, run_with_timeout
from apexquant_health.models import HealthResponse, HealthStatus


class HealthChecker:
    def __init__(
        self,
        service_name: str,
        version: str,
        plane: str,
        environment: str,
        instance_id: str,
    ) -> None:
        self._service_name = service_name
        self._version = version
        self._plane = plane
        self._environment = environment
        self._instance_id = instance_id
        self._checks: list[DependencyCheck] = []

    def add_check(self, check: DependencyCheck) -> None:
        self._checks.append(check)

    async def check_live(self) -> bool:
        # Liveness only checks if the event loop is responsive
        return True

    async def check_ready(self) -> bool:
        if not self._checks:
            return True

        results = await asyncio.gather(
            *[run_with_timeout(c.check()) for c in self._checks]
        )

        return all(r.status == HealthStatus.HEALTHY for r in results)

    async def check_health(self) -> HealthResponse:
        import asyncio
        
        results = {}
        if self._checks:
            checks = await asyncio.gather(
                *[run_with_timeout(c.check()) for c in self._checks]
            )
            for check, result in zip(self._checks, checks):
                results[f"{check.type}:{check.name}"] = result

        overall_status = HealthStatus.HEALTHY
        for result in results.values():
            if result.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
                break

        return HealthResponse(
            status=overall_status,
            service=self._service_name,
            version=self._version,
            plane=self._plane,
            environment=self._environment,
            instance_id=self._instance_id,
            dependencies=results,
        )