from __future__ import annotations

from typing import Any

SECRET_KEY_MARKERS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "credential",
    "access_key",
    "authorization",
)

REDACTED = "[REDACTED]"


def is_secret_key(key: str) -> bool:
    normalized = key.lower()

    return any(marker in normalized for marker in SECRET_KEY_MARKERS)


def redact_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}

    for key, value in attributes.items():
        if is_secret_key(key):
            redacted[key] = REDACTED
        elif isinstance(value, dict):
            redacted[key] = redact_attributes(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_attributes(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            redacted[key] = value

    return redacted