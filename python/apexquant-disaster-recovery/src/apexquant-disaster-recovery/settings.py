from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class DisasterRecoverySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APEX_DR_",
        env_file=".env",
        extra="ignore",
    )

    http_addr: str = "0.0.0.0:8094"
    environment: str = "local"

    database_url: str | None = None
    migrations_dir: str = "/migrations/postgres/disaster_recovery"
    migrate_on_start: bool = True

    default_backup_policy_name: str = "local-postgres"
    enable_health_checks: bool = False
    health_timeout_seconds: float = 2.0