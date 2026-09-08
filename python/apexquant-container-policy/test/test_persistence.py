from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from apexquant_container_policy.models import Severity, VerificationReport, Violation
from apexquant_container_policy.persistence import persist_report


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, Sequence[Any] | None]] = []
        self.committed = False

    def execute(
        self,
        query: str,
        parameters: Sequence[Any] | None = None,
        /,
    ) -> Any:
        self.executed.append((query, parameters))
        return None

    def commit(self) -> None:
        self.committed = True


def test_persist_report_writes_run_and_violations() -> None:
    now = datetime.now(timezone.utc)

    report = VerificationReport(
        compose_path="/workspace/docker-compose.yaml",
        started_at=now,
        completed_at=now,
        ok=False,
        errors_count=1,
        warnings_count=0,
        services_checked=["test-service"],
        violations=[
            Violation(
                service_name="test-service",
                code="MISSING_LABEL",
                severity=Severity.ERROR,
                message="required label is missing: apexquant.version",
            )
        ],
    )

    connection = FakeConnection()

    persist_report(connection, report)

    assert connection.committed
    assert len(connection.executed) == 2

    run_query, run_parameters = connection.executed[0]

    assert "INSERT INTO container_policy.verification_runs" in run_query
    assert run_parameters is not None
    assert run_parameters[1] == "/workspace/docker-compose.yaml"
    assert run_parameters[4] is False
    assert run_parameters[5] == 1
    assert run_parameters[6] == 0

    violation_query, violation_parameters = connection.executed[1]

    assert "INSERT INTO container_policy.verification_violations" in violation_query
    assert violation_parameters is not None
    assert violation_parameters[1] == "test-service"
    assert violation_parameters[2] == "MISSING_LABEL"
    assert violation_parameters[3] == "ERROR"