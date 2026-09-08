from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from apexquant_service_framework.service_contract import (
    FailClosedPolicy,
    ServicePlane,
)


class ServiceFrameworkSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APEX_SERVICE_",
        env_file=".env",
        extra="ignore",
    )

    service_name: str
    service_version: str = "0.1.0"
    environment: str = "sandbox"
    plane: ServicePlane = ServicePlane.AI
    fail_closed_policy: FailClosedPolicy = FailClosedPolicy.READ_ONLY
    registration_url: str | None = None
    registration_required: bool = True
    heartbeat_interval_seconds: float = 10.0

    @field_validator("service_name", "service_version", "environment")
    @classmethod
    def validate_token(cls, value: str) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("value must not be empty")

        if any(character.isspace() for character in normalized):
            raise ValueError("value must not contain whitespace")

        return normalized