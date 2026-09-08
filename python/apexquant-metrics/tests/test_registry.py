import pytest
from prometheus_client import CollectorRegistry

from apexquant_metrics.registry import (
    ApexMetricRegistry,
    MetricGovernanceError,
)


@pytest.fixture
def registry() -> ApexMetricRegistry:
    return ApexMetricRegistry(
        service_name="test-service",
        environment="local",
        plane="CONTROL",
        version="0.15.0",
        registry=CollectorRegistry(),
    )


def test_valid_metric_name(registry: ApexMetricRegistry) -> None:
    counter = registry.counter(
        name="apexquant_http_requests_total",
        description="Total HTTP requests",
    )
    assert counter is not None


def test_invalid_metric_name_rejected(registry: ApexMetricRegistry) -> None:
    with pytest.raises(MetricGovernanceError):
        registry.counter(
            name="http_requests_total",
            description="Missing apexquant prefix",
        )


def test_high_cardinality_label_rejected(registry: ApexMetricRegistry) -> None:
    with pytest.raises(MetricGovernanceError):
        registry.counter(
            name="apexquant_http_requests_total",
            description="Total HTTP requests",
            labels=("method", "request_id"),
        )


def test_standard_labels_injected(registry: ApexMetricRegistry) -> None:
    counter = registry.counter(
        name="apexquant_test_events_total",
        description="Test events",
        labels=("event_type",),
    )

    # The underlying prometheus-client library stores label names
    # We can verify by observing a value and checking the output
    child = counter.labels(event_type="test")
    child.inc()

    output = registry.prometheus_registry.get_sample_value(
        "apexquant_test_events_total",
        {
            "event_type": "test",
            "service": "test-service",
            "environment": "local",
            "plane": "CONTROL",
            "version": "0.15.0",
        },
    )

    assert output == 1.0