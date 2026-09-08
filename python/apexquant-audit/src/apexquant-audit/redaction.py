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


def redact_data(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}

        for key, item in value.items():
            if is_secret_key(str(key)):
                redacted[str(key)] = REDACTED
            else:
                redacted[str(key)] = redact_data(item)

        return redacted

    if isinstance(value, list):
        return [redact_data(item) for item in value]

    return value