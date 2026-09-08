import io
import json
import logging

from apexquant_logging.context import set_context
from apexquant_logging.formatter import JsonLogFormatter


def test_json_formatter_outputs_structured_log() -> None:
    stream = io.StringIO()

    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        JsonLogFormatter(
            service_name="test-service",
            environment="local",
            plane="CONTROL",
            service_version="0.14.0",
        )
    )

    logger = logging.getLogger("test.formatter")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    set_context(request_id="req-123")

    logger.info("hello", extra={"data": {"api_key": "secret-value", "ok": True}})

    output = stream.getvalue().strip()
    payload = json.loads(output)

    assert payload["service"] == "test-service"
    assert payload["environment"] == "local"
    assert payload["plane"] == "CONTROL"
    assert payload["event"] == "test.formatter"
    assert payload["message"] == "hello"
    assert payload["request_id"] == "req-123"
    assert payload["data"]["api_key"] == "[REDACTED]"
    assert payload["data"]["ok"] is True