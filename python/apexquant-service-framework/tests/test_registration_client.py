import httpx
import pytest

from apexquant_service_framework.registration import RegistrationClient
from apexquant_service_framework.service_contract import (
    FailClosedPolicy,
    ServiceDescriptor,
    ServicePlane,
)


@pytest.mark.asyncio
async def test_register_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/services/register"

        return httpx.Response(
            status_code=200,
            json={"registration_id": "sandbox:test-service:0.1.0"},
        )

    transport = httpx.MockTransport(handler)

    client = RegistrationClient(
        "http://service-framework",
        max_attempts=1,
        transport=transport,
    )

    descriptor = ServiceDescriptor(
        service_name="test-service",
        version="0.1.0",
        environment="sandbox",
        plane=ServicePlane.AI,
        fail_closed_policy=FailClosedPolicy.READ_ONLY,
    )

    response = await client.register(descriptor)

    assert response["registration_id"] == "sandbox:test-service:0.1.0"

    await client.aclose()


@pytest.mark.asyncio
async def test_register_failure_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=503)

    transport = httpx.MockTransport(handler)

    client = RegistrationClient(
        "http://service-framework",
        max_attempts=1,
        transport=transport,
    )

    descriptor = ServiceDescriptor(
        service_name="test-service",
        version="0.1.0",
        environment="sandbox",
        plane=ServicePlane.AI,
        fail_closed_policy=FailClosedPolicy.READ_ONLY,
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.register(descriptor)

    await client.aclose()