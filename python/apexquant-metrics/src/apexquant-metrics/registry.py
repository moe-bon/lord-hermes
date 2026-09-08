from __future__ import annotations

import re
from typing import Sequence

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, Summary

METRIC_NAME_PATTERN = re.compile(r"^apexquant_[a-z0-9_]+_[a-z0-9_]+(_[a-z]+)?$")

FORBIDDEN_HIGH_CARDINALITY_LABELS = {
    "user_id",
    "request_id",
    "trace_id",
    "correlation_id",
    "session_id",
    "ip_address",
    "email",
    "username",
}

STANDARD_LABELS = ("service", "environment", "plane", "version")


class MetricGovernanceError(Exception):
    pass


class MetricTypeError(Exception):
    pass


class ApexMetricRegistry:
    def __init__(
        self,
        service_name: str,
        environment: str,
        plane: str,
        version: str,
        registry: CollectorRegistry | None = None,
    ) -> None:
        self._service_name = service_name
        self._environment = environment
        self._plane = plane
        self._version = version
        self._registry = registry or CollectorRegistry()
        self._standard_label_values = {
            "service": service_name,
            "environment": environment,
            "plane": plane,
            "version": version,
        }

    @property
    def prometheus_registry(self) -> CollectorRegistry:
        return self._registry

    def _validate_name(self, name: str) -> None:
        if not METRIC_NAME_PATTERN.match(name):
            raise MetricGovernanceError(
                f"metric name '{name}' violates naming convention: "
                "must match apexquant_{{subsystem}}_{{name}}_{{unit}}"
            )

    def _validate_labels(self, labels: Sequence[str]) -> list[str]:
        normalized = [label.lower() for label in labels]

        for label in normalized:
            if label in FORBIDDEN_HIGH_CARDINALITY_LABELS:
                raise MetricGovernanceError(
                    f"high-cardinality label '{label}' is forbidden in Prometheus metrics"
                )

        combined = list(STANDARD_LABELS) + [
            label for label in normalized if label not in STANDARD_LABELS
        ]

        return combined

    def _inject_standard_labels(
        self,
        metric: Counter | Gauge | Histogram | Summary,
        labels: dict[str, str] | None = None,
    ) -> Counter | Gauge | Histogram | Summary | Counter.Child | Gauge.Child | Histogram.Child | Summary.Child:
        merged = dict(self._standard_label_values)

        if labels:
            merged.update(labels)

        return metric.labels(**merged)

    def counter(
        self,
        name: str,
        description: str,
        labels: Sequence[str] = (),
    ) -> Counter:
        self._validate_name(name)
        all_labels = self._validate_labels(labels)

        return Counter(
            name,
            description,
            labelnames=all_labels,
            registry=self._registry,
        )

    def gauge(
        self,
        name: str,
        description: str,
        labels: Sequence[str] = (),
    ) -> Gauge:
        self._validate_name(name)
        all_labels = self._validate_labels(labels)

        return Gauge(
            name,
            description,
            labelnames=all_labels,
            registry=self._registry,
        )

    def histogram(
        self,
        name: str,
        description: str,
        labels: Sequence[str] = (),
        buckets: Sequence[float] | None = None,
    ) -> Histogram:
        self._validate_name(name)
        all_labels = self._validate_labels(labels)

        kwargs: dict = {
            "name": name,
            "documentation": description,
            "labelnames": all_labels,
            "registry": self._registry,
        }

        if buckets is not None:
            kwargs["buckets"] = buckets

        return Histogram(**kwargs)

    def summary(
        self,
        name: str,
        description: str,
        labels: Sequence[str] = (),
    ) -> Summary:
        self._validate_name(name)
        all_labels = self._validate_labels(labels)

        return Summary(
            name,
            description,
            labelnames=all_labels,
            registry=self._registry,
        )