from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class BackupSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APEX_BACKUP_",
        env_file=".env",
        extra="ignore",
    )

    http_addr: str = "0.0.0.0:8093"
    environment: str = "local"

    database_url: str | None = None
    migrations_dir: str = "/migrations/postgres/backup_recovery"
    migrate_on_start: bool = True

    backup_workdir: str = "/tmp/apexquant-backups"
    backup_storage_root: str = "/backups"

    storage_driver: str = "local"
    default_bucket: str = "apexquant-backups"

    s3_endpoint_url: str | None = None
    s3_region: str | None = None
    s3_server_side_encryption: bool = False