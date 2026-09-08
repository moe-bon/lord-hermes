from __future__ import annotations

from enum import Enum
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from apexquant_service_framework.service_contract import ServiceDescriptor


class RegistrationState(str, Enum):
    STARTING = "STARTING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    STOPPING = "STOPPING"
    FAILED = "FAILED"


class RegistrationClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 2.0,
        max_attempts: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._max_attempts = max_attempts
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def register(self, descriptor: ServiceDescriptor) -> dict[str, Any]:
        payload = descriptor.to_registration_payload()
        return await self._request("POST", "/v1/services/register", payload)

    async def heartbeat(
        self,
        service_id: str,
        state: RegistrationState,
        detail: str = "",
    ) -> dict[str, Any]:
        payload = {
            "service_id": service_id,
            "state": state.value,
            "detail": detail,
        }

        return await self._request("POST", "/v1/services/heartbeat", payload)

    async def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, object],
    ) -> dict[str, Any]:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(multiplier=0.1, max=1.0),
            retry=retry_if_exception_type(httpx.HTTPError),
            reraise=True,
        ):
            with attempt:
                response = await self._client.request(
                    method,
                    f"{self._base_url}{path}",
                    json=payload,
                )
                response.raise_for_status()
                return dict(response.json())

        raise httpx.HTTPError("registration request failed")