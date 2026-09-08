from __future__ import annotations

import json
import uuid
from typing import Any, Protocol, Sequence

from apexquant_repo_architecture.models import VerificationReport


class DatabaseConnection(Protocol):
    def execute(
        self,
        query: str,
        parameters: Sequence[Any] | None = None,
        /,
    ) -> Any:
        raise NotImplementedError

    def commit(self) -> None:
        raise NotImplementedError


def persist_report(connection: DatabaseConnection, report: VerificationReport) -> None:
    run_id = uuid.uuid4()

    connection.execute(
        """
        INSERT INTO repository_architecture.verification_runs (
            run_id,
            repo_root,
            started_at,
            completed_at,
            ok,
            errors_count,
            warnings_count,
            checked_paths,
            cargo_members,
            python_packages,
            violations
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
        """,
        (
            run_id,
            report.repo_root,
            report.started_at,
            report.completed_at,
            report.ok,
            report.errors_count,
            report.warnings_count,
            json.dumps(report.checked_paths),
            json.dumps(report.cargo_members),
            json.dumps(report.python_packages),
            json.dumps([violation.model_dump(mode="json") for violation in report.violations]),
        ),
    )

    for violation in report.violations:
        connection.execute(
            """
            INSERT INTO repository_architecture.verification_violations (
                run_id,
                code,
                severity,
                path,
                message
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                run_id,
                violation.code,
                violation.severity.value,
                violation.path,
                violation.message,
            ),
        )

    connection.commit()