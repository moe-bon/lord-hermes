from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from apexquant_env_config.loader import extract_required_env_vars, load_manifest
from apexquant_env_config.models import (
    ConfigValidationReport,
    ConfigViolation,
    Severity,
)

REQUIRED_MANIFEST_FILENAME = "environment.yaml"


def validate_environment(
    environments_root: Path,
    environment: str,
    *,
    check_process_env: bool = False,
    process_env: Mapping[str, str] | None = None,
) -> ConfigValidationReport:
    started_at = datetime.now(timezone.utc)
    violations: list[ConfigViolation] = []
    required_env_vars: list[str] = []

    environment_dir = environments_root / environment
    manifest_path = environment_dir / REQUIRED_MANIFEST_FILENAME

    if not manifest_path.exists():
        violations.append(
            ConfigViolation(
                code="MANIFEST_MISSING",
                severity=Severity.ERROR,
                message=f"missing manifest: {manifest_path}",
                path=str(manifest_path),
            )
        )

        completed_at = datetime.now(timezone.utc)

        return ConfigValidationReport(
            environment=environment,
            manifest_path=str(manifest_path),
            started_at=started_at,
            completed_at=completed_at,
            ok=False,
            errors_count=1,
            warnings_count=0,
            required_env_vars=[],
            violations=violations,
        )

    try:
        manifest = load_manifest(manifest_path)
    except ValidationError as exc:
        for error in exc.errors():
            path = ".".join(str(item) for item in error.get("loc", []))

            violations.append(
                ConfigViolation(
                    code="SCHEMA_VALIDATION_FAILED",
                    severity=Severity.ERROR,
                    message=str(error.get("msg", "invalid configuration value")),
                    path=path or None,
                )
            )

        completed_at = datetime.now(timezone.utc)

        return ConfigValidationReport(
            environment=environment,
            manifest_path=str(manifest_path),
            started_at=started_at,
            completed_at=completed_at,
            ok=False,
            errors_count=len(violations),
            warnings_count=0,
            required_env_vars=[],
            violations=violations,
        )
    except ValueError as exc:
        violations.append(
            ConfigViolation(
                code="INVALID_MANIFEST",
                severity=Severity.ERROR,
                message=str(exc),
                path=str(manifest_path),
            )
        )

        completed_at = datetime.now(timezone.utc)

        return ConfigValidationReport(
            environment=environment,
            manifest_path=str(manifest_path),
            started_at=started_at,
            completed_at=completed_at,
            ok=False,
            errors_count=1,
            warnings_count=0,
            required_env_vars=[],
            violations=violations,
        )

    if manifest.environment.value != environment:
        violations.append(
            ConfigViolation(
                code="ENVIRONMENT_NAME_MISMATCH",
                severity=Severity.ERROR,
                message=(
                    f"manifest environment {manifest.environment.value} "
                    f"does not match directory {environment}"
                ),
                path="environment",
            )
        )

    required_env_vars = extract_required_env_vars(manifest)

    if check_process_env:
        observed_env = process_env if process_env is not None else os.environ

        for required_var in required_env_vars:
            value = observed_env.get(required_var)

            if value is None or not value.strip():
                violations.append(
                    ConfigViolation(
                        code="REQUIRED_ENV_VAR_MISSING",
                        severity=Severity.ERROR,
                        message=f"required environment variable is missing: {required_var}",
                        path=None,
                    )
                )

        apex_environment = observed_env.get("APEX_ENVIRONMENT")

        if apex_environment is not None and apex_environment != environment:
            violations.append(
                ConfigViolation(
                    code="APEX_ENVIRONMENT_MISMATCH",
                    severity=Severity.ERROR,
                    message=(
                        f"APEX_ENVIRONMENT={apex_environment} does not match "
                        f"requested environment {environment}"
                    ),
                    path=None,
                )
            )

        apex_trading_mode = observed_env.get("APEX_TRADING_MODE")

        if (
            apex_trading_mode is not None
            and apex_trading_mode != manifest.trading_mode.value
        ):
            violations.append(
                ConfigViolation(
                    code="APEX_TRADING_MODE_MISMATCH",
                    severity=Severity.ERROR,
                    message=(
                        f"APEX_TRADING_MODE={apex_trading_mode} does not match "
                        f"manifest trading mode {manifest.trading_mode.value}"
                    ),
                    path=None,
                )
            )

    completed_at = datetime.now(timezone.utc)

    errors_count = sum(
        1 for violation in violations if violation.severity == Severity.ERROR
    )
    warnings_count = sum(
        1 for violation in violations if violation.severity == Severity.WARNING
    )

    return ConfigValidationReport(
        environment=environment,
        manifest_path=str(manifest_path),
        started_at=started_at,
        completed_at=completed_at,
        ok=errors_count == 0,
        errors_count=errors_count,
        warnings_count=warnings_count,
        required_env_vars=required_env_vars,
        violations=violations,
    )