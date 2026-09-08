from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class EnvironmentName(str, Enum):
    LOCAL = "local"
    SANDBOX = "sandbox"
    PAPER = "paper"
    SHADOW = "shadow"
    PRODUCTION = "production"


class TradingMode(str, Enum):
    DEVELOPMENT = "DEVELOPMENT"
    SANDBOX = "SANDBOX"
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    PRODUCTION = "PRODUCTION"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class PostgresSslMode(str, Enum):
    DISABLE = "disable"
    REQUIRE = "require"
    VERIFY_CA = "verify-ca"
    VERIFY_FULL = "verify-full"


class KafkaSecurityProtocol(str, Enum):
    PLAINTEXT = "PLAINTEXT"
    SSL = "SSL"
    SASL_PLAINTEXT = "SASL_PLAINTEXT"
    SASL_SSL = "SASL_SSL"


class PostgresConfig(BaseModel):
    host: str
    port: int = Field(ge=1, le=65535)
    database: str
    user: str
    password: str
    ssl_mode: PostgresSslMode


class RedisConfig(BaseModel):
    host: str
    port: int = Field(ge=1, le=65535)
    database_index: int = Field(ge=0)


class KafkaConfig(BaseModel):
    bootstrap_servers: str
    security_protocol: KafkaSecurityProtocol


class ObjectStorageConfig(BaseModel):
    endpoint: str
    access_key: str
    secret_key: str
    secure: bool


class InfrastructureConfig(BaseModel):
    postgres: PostgresConfig
    redis: RedisConfig
    kafka: KafkaConfig
    object_storage: ObjectStorageConfig


class ServiceFrameworkConfig(BaseModel):
    enabled: bool
    log_level: LogLevel = LogLevel.INFO
    metrics_enabled: bool = True


class ServicesConfig(BaseModel):
    service_framework: ServiceFrameworkConfig


class EnvironmentManifest(BaseModel):
    environment: EnvironmentName
    display_name: str
    trading_mode: TradingMode
    live_capital_allowed: bool
    fail_closed_default: bool
    risk_enforcement_required: bool
    ai_direct_execution_allowed: bool
    observability_required: bool
    networks: dict[str, str]
    services: ServicesConfig
    infrastructure: InfrastructureConfig

    @model_validator(mode="after")
    def enforce_environment_policy(self) -> EnvironmentManifest:
        expected_trading_mode = {
            EnvironmentName.LOCAL: TradingMode.DEVELOPMENT,
            EnvironmentName.SANDBOX: TradingMode.SANDBOX,
            EnvironmentName.PAPER: TradingMode.PAPER,
            EnvironmentName.SHADOW: TradingMode.SHADOW,
            EnvironmentName.PRODUCTION: TradingMode.PRODUCTION,
        }

        if self.trading_mode != expected_trading_mode[self.environment]:
            raise ValueError(
                f"environment {self.environment.value} must use trading mode "
                f"{expected_trading_mode[self.environment].value}"
            )

        if self.live_capital_allowed and self.environment != EnvironmentName.PRODUCTION:
            raise ValueError("live capital is only permitted in production")

        if self.ai_direct_execution_allowed:
            raise ValueError("AI direct execution is forbidden")

        if not self.risk_enforcement_required:
            raise ValueError("risk enforcement is required in every environment")

        if not self.observability_required:
            raise ValueError("observability is required in every environment")

        if not self.fail_closed_default and self.environment in {
            EnvironmentName.PAPER,
            EnvironmentName.SHADOW,
            EnvironmentName.PRODUCTION,
        }:
            raise ValueError("fail_closed_default must be true for critical environments")

        required_networks = {"platform", "data", "observability"}

        if set(self.networks.keys()) != required_networks:
            raise ValueError(
                "networks must define exactly platform, data, and observability"
            )

        for network_name in self.networks.values():
            if not network_name.strip():
                raise ValueError("network names must not be empty")

        secured_environments = {
            EnvironmentName.PAPER,
            EnvironmentName.SHADOW,
            EnvironmentName.PRODUCTION,
        }

        if self.environment in secured_environments:
            if self.infrastructure.postgres.ssl_mode not in {
                PostgresSslMode.REQUIRE,
                PostgresSslMode.VERIFY_CA,
                PostgresSslMode.VERIFY_FULL,
            }:
                raise ValueError("postgres SSL must be enabled for critical environments")

            if self.infrastructure.kafka.security_protocol not in {
                KafkaSecurityProtocol.SSL,
                KafkaSecurityProtocol.SASL_SSL,
            }:
                raise ValueError("Kafka must use TLS for critical environments")

            if not self.infrastructure.object_storage.secure:
                raise ValueError(
                    "object storage must use secure transport for critical environments"
                )

        return self


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class ConfigViolation(BaseModel):
    code: str
    severity: Severity
    message: str
    path: str | None = None


class ConfigValidationReport(BaseModel):
    environment: str
    manifest_path: str
    started_at: datetime
    completed_at: datetime
    ok: bool
    errors_count: int = Field(default=0, ge=0)
    warnings_count: int = Field(default=0, ge=0)
    required_env_vars: list[str] = Field(default_factory=list)
    violations: list[ConfigViolation] = Field(default_factory=list)