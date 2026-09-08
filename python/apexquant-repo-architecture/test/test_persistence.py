from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from apexquant_repo_architecture.models import (
    Severity,
    VerificationReport,
    Violation,
)
from apexquant_repo_architecture.persistence import persist_report


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
        repo_root="/tmp/apexquant-ultra",
        started_at=now,
        completed_at=now,
        ok=False,
        errors_count=1,
        warnings_count=1,
        violations=[
            Violation(
                code="MISSING_FILE",
                severity=Severity.ERROR,
                path="Makefile",
                message="required file is missing",
            ),
            Violation(
                code="UNEXPECTED_TOP_LEVEL_ENTRY",
                severity=Severity.WARNING,
                path="unexpected-directory",
                message="unexpected top-level repository entry",
            ),
        ],
        checked_paths=["Makefile"],
        cargo_members=["crates/control/service-framework-core"],
        python_packages=["apexquant-service-framework"],
    )

    connection = FakeConnection()

    persist_report(connection, report)

    assert connection.committed
    assert len(connection.executed) == 3

    run_query, run_parameters = connection.executed[0]

    assert "INSERT INTO repository_architecture.verification_runs" in run_query
    assert run_parameters is not None
    assert run_parameters[1] == "/tmp/apexquant-ultra"
    assert run_parameters[4] is False
    assert run_parameters[5] == 1
    assert run_parameters[6] == 1

    first_violation_query, first_violation_parameters = connection.executed[1]

    assert "INSERT INTO repository_architecture.verification_violations" in first_violation_query
    assert first_violation_parameters is not None
    assert first_violation_parameters[1] == "MISSING_FILE"
    assert first_violation_parameters[2] == "ERROR"