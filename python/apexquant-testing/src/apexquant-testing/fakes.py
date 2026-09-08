from __future__ import annotations

from typing import Any


class FakeKeyValueStore:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def delete(self, key: str) -> bool:
        return self._data.pop(key, None) is not None

    def exists(self, key: str) -> bool:
        return key in self._data

    def clear(self) -> None:
        self._data.clear()


class FakeEventPublisher:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self.published.append({"topic": topic, "payload": payload})

    def clear(self) -> None:
        self.published.clear()

    def topics(self) -> list[str]:
        return [event["topic"] for event in self.published]