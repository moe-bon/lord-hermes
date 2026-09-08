from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class TracingCoreSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APEX_TRACING_",
        env_file=".env",
        extra="ignore",
    )

    http_addr: str = "0.0.0.0:8089"
    environment: str = "local"

    service_name: str = "tracing-core"
    plane: str = "OBSERVABILITY"
    service_version: str = "0.16.0"

    database_url: str | None = None
    migrations_dir: str = "/migrations/postgres/tracing"

    otlp_endpoint: str | None = None
    tempo_query_endpoint: str | None = None

    sample_ratio: float = 1.0