from fastapi.testclient import TestClient

from apexquant_tracing.core.app import TracingCoreSettings, create_tracing_core_app


def build_settings() -> TracingCoreSettings:
    return TracingCoreSettings(
        http_addr="0.0.0.0:8089",
        environment="local",
        database_url=None,
        otlp_endpoint=None,
        tempo_query_endpoint=None,
        sample_ratio=1.0,
    )


def test_health_endpoint() -> None:
    app = create_tracing_core_app(build_settings())

    with TestClient(app) as client:
        response = client.get("/healthz")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_verify_valid_context() -> None:
    app = create_tracing_core_app(build_settings())

    with TestClient(app) as client:
        response = client.post(
            "/v1/tracing/context/verify",
            json={
                "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
            },
        )

        assert response.status_code == 200

        payload = response.json()

        assert payload["valid"] is True
        assert payload["trace_id"] == "0af7651916cd43dd8448eb211c80319c"
        assert payload["sampled"] is True


def test_create_test_span() -> None:
    app = create_tracing_core_app(build_settings())

    with TestClient(app) as client:
        response = client.post(
            "/v1/tracing/test-span",
            json={"name": "apex.tracing.test"},
        )

        assert response.status_code == 200

        payload = response.json()

        assert len(payload["trace_id"]) == 32
        assert len(payload["span_id"]) == 16