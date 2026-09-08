import pytest
import asyncio

from apexquant_health.checker import HealthChecker
from apexquant_health.checks import DependencyCheck, DependencyStatus, HealthStatus
from apexquant_health.models import HealthResponse


class MockHealthyCheck(DependencyCheck):
    @property
    def name(self) -> str: return "mock-db"

    @property
    def type(self) -> str: return "postgres"

    async def check(self) -> DependencyStatus:
        await asyncio.sleep(0.01)
        return DependencyStatus(status=HealthStatus.HEALTHY, latency_ms=10.0)


class MockFailingCheck(DependencyCheck):
    @property
    def name(self) -> str: return "mock-redis"

    @property
    def type(self) -> str: return "redis"

    async def check(self) -> DependencyStatus:
        return DependencyStatus(status=HealthStatus.UNHEALTHY, error="connection refused")


@pytest.mark.asyncio
async def test_checker_healthy() -> None:
    checker = HealthChecker("test-svc", "1.0", "CONTROL", "local", "inst-1")
    checker.add_check(MockHealthyCheck())

    assert await checker.check_ready() is True
    
    response = await checker.check_health()
    assert response.status == HealthStatus.HEALTHY
    assert "postgres:mock-db" in response.dependencies


@pytest.mark.asyncio
async def test_checker_unhealthy() -> None:
    checker = HealthChecker("test-svc", "1.0", "CONTROL", "local", "inst-1")
    checker.add_check(MockHealthyCheck())
    checker.add_check(MockFailingCheck())

    assert await checker.check_ready() is False
    
    response = await checker.check_health()
    assert response.status == HealthStatus.UNHEALTHY
    assert response.dependencies["redis:mock-redis"].status == HealthStatus.UNHEALTHY