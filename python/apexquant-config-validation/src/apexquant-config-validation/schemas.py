from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from apexquant_config_validation.models import Severity, ValidationIssue

SCHEMA_FILES = {
    "service_manifest/v1": "service_manifest.schema.json",
    "environment_manifest/v1": "environment_manifest.schema.json",
}


def _packaged_schema_text(filename: str) -> str | None:
    try:
        from importlib import resources

        ref = resources.files("apexquant_config_validation").joinpath(
            f"data/schemas/{filename}"
        )
        return ref.read_text(encoding="utf-8")
    except Exception:
        return None


def _repo_schema_text(filename: str) -> str | None:
    here = Path(__file__).resolve()

    candidates = [
        here.parents[4] / "data/schemas/config" / filename,
        here.parents[5] / "data/schemas/config" / filename,
        Path.cwd() / "data/schemas/config" / filename,
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")

    return None


def load_schema(schema_key: str) -> dict:
    filename = SCHEMA_FILES.get(schema_key)

    if filename is None:
        raise KeyError(f"unknown schema_key: {schema_key}")

    text = _packaged_schema_text(filename) or _repo_schema_text(filename)

    if text is None:
        raise FileNotFoundError(f"schema file not found: {filename}")

    return json.loads(text)


def validate_json_schema(document: dict, schema_key: str) -> list[ValidationIssue]:
    schema = load_schema(schema_key)
    validator = Draft202012Validator(schema)

    issues: list[ValidationIssue] = []

    for error in sorted(validator.iter_errors(document), key=lambda e: list(e.path)):
        if error.path:
            path = "$." + ".".join(str(part) for part in error.path)
        else:
            path = "$"

        issues.append(
            ValidationIssue(
                severity=Severity.ERROR,
                path=path,
                message=error.message,
            )
        )

    return issues