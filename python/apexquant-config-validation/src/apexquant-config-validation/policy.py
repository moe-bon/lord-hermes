from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from apexquant_config_validation.models import Severity, ValidationIssue

_POLICY_CACHE: ValidationPolicy | None = None


class ValidationPolicy(BaseModel):
    version: int
    secret_key_markers: list[str]
    allowed_secret_reference_prefixes: list[str]
    environments: list[str]
    planes: list[str]
    fail_closed_policies: list[str]
    trading_mode_by_environment: dict[str, str]
    require_fail_closed_for: list[str]


def _packaged_policy_text() -> str | None:
    try:
        from importlib import resources

        ref = resources.files("apexquant_config_validation").joinpath(
            "data/validation_policy.yaml"
        )
        return ref.read_text(encoding="utf-8")
    except Exception:
        return None


def _repo_policy_text() -> str | None:
    here = Path(__file__).resolve()

    candidates = [
        here.parents[4] / "data/config/validation_policy.yaml",
        here.parents[5] / "data/config/validation_policy.yaml",
        Path.cwd() / "data/config/validation_policy.yaml",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")

    return None


def load_policy() -> ValidationPolicy:
    global _POLICY_CACHE

    if _POLICY_CACHE is not None:
        return _POLICY_CACHE

    text = _packaged_policy_text() or _repo_policy_text()

    if text is None:
        raise FileNotFoundError("validation_policy.yaml not found")

    _POLICY_CACHE = ValidationPolicy.model_validate(yaml.safe_load(text))

    return _POLICY_CACHE


def is_secret_key(key: str, policy: ValidationPolicy) -> bool:
    normalized = key.lower()

    return any(marker in normalized for marker in policy.secret_key_markers)


def is_secret_reference(value: Any, policy: ValidationPolicy) -> bool:
    if not isinstance(value, str):
        return False

    if value.startswith("${") and value.endswith("}"):
        return True

    return any(value.startswith(prefix) for prefix in policy.allowed_secret_reference_prefixes)


def scan_secrets(
    value: Any,
    policy: ValidationPolicy,
    path: str = "$",
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if isinstance(value, dict):
        for key, item in value.items():
            key_path = f"{path}.{key}"

            if is_secret_key(str(key), policy):
                if isinstance(item, str) and not is_secret_reference(item, policy):
                    issues.append(
                        ValidationIssue(
                            severity=Severity.ERROR,
                            path=key_path,
                            message=(
                                "literal secret detected; use env://, vault://, "
                                "secret://, or ${VAR} references only"
                            ),
                        )
                    )
                    continue

            issues.extend(scan_secrets(item, policy, key_path))

        return issues

    if isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(scan_secrets(item, policy, f"{path}[{index}]"))

        return issues

    return issues