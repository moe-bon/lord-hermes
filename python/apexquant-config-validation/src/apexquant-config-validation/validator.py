from __future__ import annotations

from typing import Any

from apexquant_config_validation.canonical import hash_config
from apexquant_config_validation.models import (
    Severity,
    ValidationIssue,
    ValidationReport,
)
from apexquant_config_validation.policy import (
    ValidationPolicy,
    load_policy,
    scan_secrets,
)
from apexquant_config_validation.schemas import SCHEMA_FILES, validate_json_schema


class ConfigValidator:
    def __init__(self, policy: ValidationPolicy | None = None) -> None:
        self._policy = policy or load_policy()

    def validate(self, schema_key: str, document: dict[str, Any]) -> ValidationReport:
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []

        if schema_key not in SCHEMA_FILES:
            errors.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    path="$.schema_version",
                    message=f"unknown schema_key: {schema_key}",
                )
            )
        else:
            errors.extend(validate_json_schema(document, schema_key))

        errors.extend(scan_secrets(document, self._policy))

        if schema_key == "service_manifest/v1":
            errors.extend(self._validate_service_manifest(document))

        if schema_key == "environment_manifest/v1":
            errors.extend(self._validate_environment_manifest(document))

        config_hash = hash_config(document)

        return ValidationReport(
            schema_key=schema_key,
            ok=len(errors) == 0,
            config_hash=config_hash,
            errors=errors,
            warnings=warnings,
        )

    def _validate_service_manifest(self, document: dict[str, Any]) -> list[ValidationIssue]:
        if not isinstance(document, dict):
            return []

        errors: list[ValidationIssue] = []

        schema_version = document.get("schema_version")
        if schema_version != "service_manifest/v1":
            errors.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    path="$.schema_version",
                    message="schema_version must be service_manifest/v1",
                )
            )

        environment = document.get("environment")
        if environment not in self._policy.environments:
            errors.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    path="$.environment",
                    message=f"environment must be one of {self._policy.environments}",
                )
            )

        plane = document.get("plane")
        if plane not in self._policy.planes:
            errors.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    path="$.plane",
                    message=f"plane must be one of {self._policy.planes}",
                )
            )

        fail_closed_policy = document.get("fail_closed_policy")
        if fail_closed_policy not in self._policy.fail_closed_policies:
            errors.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    path="$.fail_closed_policy",
                    message=(
                        "fail_closed_policy must be one of "
                        f"{self._policy.fail_closed_policies}"
                    ),
                )
            )

        live_trading_allowed = bool(document.get("live_trading_allowed", False))

        if live_trading_allowed and environment != "production":
            errors.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    path="$.live_trading_allowed",
                    message="live_trading_allowed may only be true in production",
                )
            )

        return errors

    def _validate_environment_manifest(self, document: dict[str, Any]) -> list[ValidationIssue]:
        if not isinstance(document, dict):
            return []

        errors: list[ValidationIssue] = []

        schema_version = document.get("schema_version")
        if schema_version != "environment_manifest/v1":
            errors.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    path="$.schema_version",
                    message="schema_version must be environment_manifest/v1",
                )
            )

        environment = document.get("environment")
        if environment not in self._policy.environments:
            errors.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    path="$.environment",
                    message=f"environment must be one of {self._policy.environments}",
                )
            )

        trading_mode = document.get("trading_mode")
        expected_trading_mode = self._policy.trading_mode_by_environment.get(environment)

        if expected_trading_mode is not None and trading_mode != expected_trading_mode:
            errors.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    path="$.trading_mode",
                    message=(
                        f"environment {environment} must use trading mode "
                        f"{expected_trading_mode}"
                    ),
                )
            )

        live_capital_allowed = bool(document.get("live_capital_allowed", False))

        if live_capital_allowed and environment != "production":
            errors.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    path="$.live_capital_allowed",
                    message="live_capital_allowed may only be true in production",
                )
            )

        fail_closed_default = document.get("fail_closed_default")

        if environment in self._policy.require_fail_closed_for and fail_closed_default is not True:
            errors.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    path="$.fail_closed_default",
                    message=(
                        f"environment {environment} must have fail_closed_default=true"
                    ),
                )
            )

        observability_required = document.get("observability_required", True)

        if observability_required is not True:
            errors.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    path="$.observability_required",
                    message="observability_required must be true",
                )
            )

        return errors