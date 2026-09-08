from __future__ import annotations

FAILURE_MODES: list[dict[str, str]] = [
    {
        "failure_mode": "network_partition",
        "category": "network",
        "description": "Network connectivity between services is lost.",
        "severity": "CRITICAL",
    },
    {
        "failure_mode": "dependency_timeout",
        "category": "timeout",
        "description": "A required dependency does not respond within the allowed budget.",
        "severity": "CRITICAL",
    },
    {
        "failure_mode": "duplicate_event",
        "category": "idempotency",
        "description": "The same event or command is delivered more than once.",
        "severity": "CRITICAL",
    },
    {
        "failure_mode": "corrupted_payload",
        "category": "data_integrity",
        "description": "Payload fails schema, checksum, or semantic validation.",
        "severity": "CRITICAL",
    },
    {
        "failure_mode": "missing_field",
        "category": "data_integrity",
        "description": "A required field is absent from an event or command.",
        "severity": "CRITICAL",
    },
    {
        "failure_mode": "stale_state",
        "category": "consistency",
        "description": "State is older than the allowed freshness window.",
        "severity": "CRITICAL",
    },
    {
        "failure_mode": "restart_mid_operation",
        "category": "recovery",
        "description": "Service restarts while an operation is in flight.",
        "severity": "CRITICAL",
    },
    {
        "failure_mode": "clock_skew",
        "category": "time",
        "description": "System clocks diverge beyond tolerance.",
        "severity": "WARNING",
    },
    {
        "failure_mode": "nan_or_infinite_input",
        "category": "input_validation",
        "description": "Numeric input is NaN or infinite.",
        "severity": "CRITICAL",
    },
    {
        "failure_mode": "unauthorized_access",
        "category": "security",
        "description": "Caller lacks required authentication or authorization.",
        "severity": "CRITICAL",
    },
    {
        "failure_mode": "rate_limit_exceeded",
        "category": "capacity",
        "description": "Caller exceeds allowed request or event rate.",
        "severity": "WARNING",
    },
    {
        "failure_mode": "broker_disconnection",
        "category": "external_dependency",
        "description": "Broker or exchange connection is lost.",
        "severity": "CRITICAL",
    },
    {
        "failure_mode": "database_unavailable",
        "category": "external_dependency",
        "description": "Primary transactional database is unavailable.",
        "severity": "CRITICAL",
    },
    {
        "failure_mode": "event_bus_unavailable",
        "category": "external_dependency",
        "description": "Kafka/Redpanda event backbone is unavailable.",
        "severity": "CRITICAL",
    },
    {
        "failure_mode": "secret_unavailable",
        "category": "security",
        "description": "Required secret or key material is unavailable.",
        "severity": "CRITICAL",
    },
]