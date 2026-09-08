from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from apexquant_logging.context import get_context
from apexquant_logging.redaction import redact_data


class JsonLogFormatter(logging.Formatter):
    def __init__(
        self,
        service_name: str,
        environment: str,
        plane: str,
        service_version: str = "unknown",
    ) -> None:
        super().__init__()

        self._service_name = service_name
        self._environment = environment
        self._plane = plane
        self._service_version = service_version

    def format(self, record: logging.LogRecord) -> str:
        context = get_context()

        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self._service_name,
            "service_version": self._service_version,
            "environment": self._environment,
            "plane": self._plane,
            "event": record.name,
            "message": record.getMessage(),
            "trace_id": context.get("trace_id"),
            "request_id": context.get("request_id"),
            "correlation_id": context.get("correlation_id"),
            "actor_id": context.get("actor_id"),
            "data": {},
        }

        if hasattr(record, "data"):
            payload["data"] = redact_data(getattr(record, "data"))

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True, default=str)