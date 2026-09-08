from __future__ import annotations

from urllib.parse import urlparse, urlunparse


def redact_url(value: str) -> str:
    parsed = urlparse(value)

    if not parsed.password:
        return value

    username = parsed.username or ""
    hostname = parsed.hostname or ""

    if parsed.port:
        netloc = f"{username}:***@{hostname}:{parsed.port}"
    else:
        netloc = f"{username}:***@{hostname}"

    return urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def redact_command(command: list[str]) -> list[str]:
    redacted: list[str] = []

    for arg in command:
        if "://" in arg:
            redacted.append(redact_url(arg))
        else:
            redacted.append(arg)

    return redacted