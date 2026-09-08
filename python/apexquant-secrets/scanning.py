from __future__ import annotations

from pathlib import Path

SECRET_KEY_MARKERS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "credential",
    "access_key",
)

SECRET_REFERENCE_PREFIXES = (
    "${",
    "vault://",
    "secret://",
    "env://",
)


class SecretScanViolation:
    def __init__(self, path: Path, line_number: int, key: str, message: str) -> None:
        self.path = path
        self.line_number = line_number
        self.key = key
        self.message = message

    def __str__(self) -> str:
        return f"{self.path}:{self.line_number} {self.key}: {self.message}"


def is_secret_reference(value: str) -> bool:
    normalized = value.strip()

    if not normalized:
        return False

    return any(normalized.startswith(prefix) for prefix in SECRET_REFERENCE_PREFIXES)


def scan_env_file(path: Path, allow_examples: bool = False) -> list[SecretScanViolation]:
    if allow_examples and path.name.endswith(".example"):
        return []

    violations: list[SecretScanViolation] = []

    text = path.read_text(encoding="utf-8")

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        normalized_key = key.lower()

        if not any(marker in normalized_key for marker in SECRET_KEY_MARKERS):
            continue

        if not value:
            continue

        if is_secret_reference(value):
            continue

        violations.append(
            SecretScanViolation(
                path=path,
                line_number=line_number,
                key=key,
                message="literal secret detected; use a secret reference instead",
            )
        )

    return violations