from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APEX_REDIS_",
        env_file=".env",
        extra="ignore",
    )

    url: str = "redis://localhost:6379/0"
    max_retries: int = 3
    socket_timeout: float = 2.0
    socket_connect_timeout: float = 2.0

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Redis URL must not be empty")
        return normalized