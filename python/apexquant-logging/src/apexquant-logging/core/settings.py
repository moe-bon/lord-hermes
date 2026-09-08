from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class LoggingCoreSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APEX_LOGGING_",
        env_file=".env",
        extra="ignore",
    )

    http_addr: str = "0.0.0.0:8088"
    environment: str = "local"

    database_url: str | None = None
    migrations_dir: str = "/migrations/postgres/logging"

    clickhouse_url: str | None = None
    clickhouse_database: str = "logging"

    stdout_enabled: bool = True
    file_sink_path: str | None = None

    strict_mode: bool = False
    max_batch_size: int = 1000repository