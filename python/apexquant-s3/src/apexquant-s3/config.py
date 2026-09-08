from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class S3Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APEX_S3_",
        env_file=".env",
        extra="ignore",
    )

    endpoint_url: str = "http://localhost:9000"
    access_key_id: str = "apex"
    secret_access_key: str = "apexquant-minio"
    region: str = "us-east-1"
    secure: bool = False
    force_path_style: bool = True

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("S3 endpoint URL must not be empty")
        return normalized