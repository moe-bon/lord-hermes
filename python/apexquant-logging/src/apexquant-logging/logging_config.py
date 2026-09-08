from __future__ import annotations

import logging

from apexquant_logging.formatter import JsonLogFormatter


def configure_logging(
    service_name: str,
    environment: str,
    plane: str,
    service_version: str = "unknown",
    level: str = "INFO",
) -> None:
    formatter = JsonLogFormatter(
        service_name=service_name,
        environment=environment,
        plane=plane,
        service_version=service_version,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True