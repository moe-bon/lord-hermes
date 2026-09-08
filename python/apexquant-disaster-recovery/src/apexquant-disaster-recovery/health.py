from __future__ import annotations

from typing import Protocol

import httpx

from apexquant_disaster_recovery.models import RecoveryComponent


class HealthChecker(Protocol):
    def check(self, component: RecoveryComponent) -> bool | None:
        raise NotImplementedError


class NullHealthChecker:
    def check(self, component: RecoveryComponent) -> bool | None:
        return None


class HttpHealthChecker:
    def __init__(self, timeout_seconds: float = 2.0) -> None:
        self._timeout_seconds = timeout_seconds

    def check(self, component: RecoveryComponent) -> bool | None:
        if not component.health_endpoint:
            return None

        try:
            response = httpx.get(
                component.health_endpoint,
                timeout=self._timeout_seconds,
            )

            return response.status_code == 200
        except Exception:
            return False