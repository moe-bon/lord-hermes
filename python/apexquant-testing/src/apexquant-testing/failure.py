from __future__ import annotations

from typing import Any


class SimulatedFailure(Exception):
    pass


def duplicate_event(event: dict[str, Any], copies: int = 1) -> list[dict[str, Any]]:
    if copies < 1:
        raise ValueError("copies must be at least 1")

    return [event] + [event] * copies


def duplicate_events(
    events: list[dict[str, Any]],
    index: int = 0,
    copies: int = 1,
) -> list[dict[str, Any]]:
    if not events:
        return []

    if index < 0 or index >= len(events):
        raise IndexError("duplicate index out of range")

    if copies < 1:
        raise ValueError("copies must be at least 1")

    duplicated = list(events)
    duplicated.extend([events[index]] * copies)

    return duplicated


def corrupt_payload(
    payload: dict[str, Any],
    key: str = "price",
    corrupt_value: Any = float("nan"),
) -> dict[str, Any]:
    corrupted = dict(payload)

    if key in corrupted:
        corrupted[key] = corrupt_value

    return corrupted


def remove_required_fields(
    payload: dict[str, Any],
    keys: list[str],
) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in keys}


def inject_timeout(message: str = "simulated timeout") -> None:
    raise TimeoutError(message)


def inject_dependency_unavailable(dependency: str) -> None:
    raise SimulatedFailure(f"dependency unavailable: {dependency}")