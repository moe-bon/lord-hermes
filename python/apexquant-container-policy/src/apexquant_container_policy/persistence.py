from __future__ import annotations

import json
import uuid
from typing import Any, Protocol, Sequence

from apexquant_container_policy.models import VerificationReport


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
        INSERT INTO container_policy.verification_runs (
            run_id,
            compose_path,
            started_at,
            completed_at,
            ok,
            errors_count,
            warnings_count,
            services_checked,
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
            %s
        )
        """,
        (
            run_id,
            report.compose_path,
            report.started_at,
            report.completed_at,
            report.ok,
            report.errors_count,
            report.warnings_count,
            json.dumps(report.services_checked),
            json.dumps([violation.model_dump(mode="json") for violation in report.violations]),
        ),
    )

    for violation in report.violations:
        connection.execute(
            """
            INSERT INTO container_policy.verification_violations (
                run_id,
                service_name,
                code,
                severity,
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
                violation.service_name,
                violation.code,
                violation.severity.value,
                violation.message,
            ),
        )

    connection.commit()