import json
from pathlib import Path

from fastapi.testclient import TestClient

from apexquant_logging.core.app import LoggingCoreSettings, create_logging_core_app


def build_settings(tmp_path: Path) -> LoggingCoreSettings:
    return LoggingCoreSettings(
        http_addr="0.0.0.0:8088",
        environment="local",
        database_url=None,
        clickhouse_url=None,
        stdout_enabled=False,
        file_sink_path=str(tmp_path / "structured.log"),
        strict_mode=False,
        max_batch_size=10,
    )


def test_ingest_valid_logs(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    app = create_logging_core_app(settings)

    with TestClient(app) as client:
        response = client.post(
            "/v1/logs",
            json={
                "logs": [
                    {
                        "level": "INFO",
                        "service": "test-service",
                        "environment": "local",
                        "plane": "CONTROL",
                        "event": "test.event",
                        "message": "test message",
                        "data": {
                            "password": "secret",
                            "ok": True,
                        },
                    }
                ]
            },
        )

        assert response.status_code == 200
        assert response.json()["accepted"] == 1

    log_file = Path(settings.file_sink_path)
    assert log_file.exists()

    line = log_file.read_text(encoding="utf-8").strip()
    payload = json.loads(line)

    assert payload["service"] == "test-service"
    assert payload["data"]["password"] == "[REDACTED]"
    assert payload["data"]["ok"] is True


def test_rejects_invalid_log_level(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    app = create_logging_core_app(settings)

    with TestClient(app) as client:
        response = client.post(
            "/v1/logs",
            json={
                "logs": [
                    {
                        "level": "INVALID",
                        "service": "test-service",
                        "environment": "local",
                        "plane": "CONTROL",
                        "event": "test.event",
                        "message": "test message",
                    }
                ]
            },
        )

        assert response.status_code == 422


def test_rejects_oversized_batch(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    settings.max_batch_size = 1

    app = create_logging_core_app(settings)

    with TestClient(app) as client:
        response = client.post(
            "/v1/logs",
            json={
                "logs": [
                    {
                        "level": "INFO",
                        "service": "test-service",
                        "environment": "local",
                        "plane": "CONTROL",
                        "event": "test.event",
                        "message": "one",
                    },
                    {
                        "level": "INFO",
                        "service": "test-service",
                        "environment": "local",
                        "plane": "CONTROL",
                        "event": "test.event",
                        "message": "two",
                    },
                ]
            },
        )

        assert response.status_code == 400