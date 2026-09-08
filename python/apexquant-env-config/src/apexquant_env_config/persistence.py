from __future__ import annotations

import json
import uuid
from typing import Any, Protocol, Sequence

from apexquant_env_config.models import ConfigValidationReport, EnvironmentManifest


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


def register_environment(
    connection: DatabaseConnection,
    manifest: EnvironmentManifest,
) -> None:
    connection.execute(
        """
        INSERT INTO config_management.environments (
            environment_name,
            display_name,
            trading_mode,
            live_capital_allowed,
            fail_closed_default,
            risk_enforcement_required,
            ai_direct_execution_allowed,
            observability_required,
            manifest
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
        ON CONFLICT (environment_name) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            trading_mode = EXCLUDED.trading_mode,
            live_capital_allowed = EXCLUDED.live_capital_allowed,
            fail_closed_default = EXCLUDED.fail_closed_default,
            risk_enforcement_required = EXCLUDED.risk_enforcement_required,
            ai_direct_execution_allowed = EXCLUDED.ai_direct_execution_allowed,
            observability_required = EXCLUDED.observability_required,
            manifest = EXCLUDED.manifest
        """,
        (
            manifest.environment.value,
            manifest.display_name,
            manifest.trading_mode.value,
            manifest.live_capital_allowed,
            manifest.fail_closed_default,
            manifest.risk_enforcement_required,
            manifest.ai_direct_execution_allowed,
            manifest.observability_required,
            manifest.model_dump_json(),
        ),
    )

    connection.commit()


def persist_validation_report(
    connection: DatabaseConnection,
    report: ConfigValidationReport,
) -> None:
    run_id = uuid.uuid4()

    connection.execute(
        """
        INSERT INTO config_management.validation_runs (
            run_id,
            environment_name,
            manifest_path,
            started_at,
            completed_at,
            ok,
            errors_count,
            warnings_count,
            required_env_vars,
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
            %s
        )
        """,
        (
            run_id,
            report.environment,
            report.manifest_path,
            report.started_at,
            report.completed_at,
            report.ok,
            report.errors_count,
            report.warnings_count,
            json.dumps(report.required_env_vars),
            json.dumps(
                [violation.model_dump(mode="json") for violation in report.violations]
            ),
        ),
    )

    for violation in report.violations:
        connection.execute(
            """
            INSERT INTO config_management.validation_violations (
                run_id,
                code,
                severity,
                message,
                path
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
                violation.message,
                violation.path,
            ),
        )

    connection.commit()