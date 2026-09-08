from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge


class ServiceMetrics:
    def __init__(self, registry: CollectorRegistry, service_name: str) -> None:
        self.registry = registry
        self.service_name = service_name

        self.requests_total = Counter(
            "apex_service_requests_total",
            "HTTP requests handled by the service",
            labelnames=("method", "path", "status"),
            registry=registry,
        )

        self.ready = Gauge(
            "apex_service_ready",
            "Readiness state of the service",
            registry=registry,
        )

        self.info = Gauge(
            "apex_service_info",
            "Service metadata",
            labelnames=("service_name", "environment", "plane"),
            registry=registry,
        )

    def set_info(self, environment: str, plane: str) -> None:
        self.info.labels(
            service_name=self.service_name,
            environment=environment,
            plane=plane,
        ).set(1)