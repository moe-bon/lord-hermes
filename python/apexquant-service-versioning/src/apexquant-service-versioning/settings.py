from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceVersioningSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APEX_SERVICE_VERSIONING_",
        env_file=".env",
        extra="ignore",
    )

    http_addr: str = "0.0.0.0:8090"
    environment: str = "local"
    database_url: str | None = None
    migrations_dir: str = "/migrations/postgres/service_versioning"
    migrate_on_start: bool = True