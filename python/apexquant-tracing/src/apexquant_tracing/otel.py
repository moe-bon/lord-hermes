from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


def configure_tracing(
    service_name: str,
    environment: str,
    plane: str,
    service_version: str,
    otlp_endpoint: str | None = None,
    sample_ratio: float = 1.0,
) -> TracerProvider:
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
            "deployment.environment": environment,
            "apex.plane": plane,
        }
    )

    sampler = ParentBased(TraceIdRatioBased(sample_ratio))

    provider = TracerProvider(
        resource=resource,
        sampler=sampler,
    )

    if otlp_endpoint:
        endpoint = f"{otlp_endpoint.rstrip('/')}/v1/traces"

        exporter = OTLPSpanExporter(endpoint=endpoint)

        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)

    set_global_textmap(
        CompositePropagator(
            [
                TraceContextTextMapPropagator(),
            ]
        )
    )

    return provider


def shutdown_tracing(provider: TracerProvider | None = None) -> None:
    target = provider or trace.get_tracer_provider()

    if hasattr(target, "shutdown"):
        target.shutdown()