from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class ServicePlane(str, Enum):
    CONTROL = "CONTROL"
    MARKET_DATA = "MARKET_DATA"
    TRADING = "TRADING"
    RISK = "RISK"
    AI = "AI"
    DATA_RESEARCH = "DATA_RESEARCH"
    OBSERVABILITY = "OBSERVABILITY"


class ServiceState(str, Enum):
    STARTING = "STARTING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    STOPPING = "STOPPING"
    FAILED = "FAILED"


class FailClosedPolicy(str, Enum):
    READ_ONLY = "READ_ONLY"
    CANCEL_OPEN_ORDERS = "CANCEL_OPEN_ORDERS"
    HALT_TRADING = "HALT_TRADING"
    SHUTDOWN = "SHUTDOWN"


class ServiceEndpoint(BaseModel):
    name: str
    protocol: str
    uri: str
    port: int = Field(ge=0, le=65535)


EXECUTION_PRIVILEGES = {
    "BROKER_WRITE",
    "EXECUTION_WRITE",
    "ORDER_SUBMIT",
    "ORDER_MODIFY",
    "ORDER_CANCEL",
}

AI_FORBIDDEN_PRIVILEGES = EXECUTION_PRIVILEGES | {
    "RISK_OVERRIDE",
    "KILL_SWITCH",
    "TRADING_WRITE",
}


class ServiceDescriptor(BaseModel):
    service_id: str | None = None
    service_name: str
    version: str
    environment: str
    plane: ServicePlane
    fail_closed_policy: FailClosedPolicy
    description: str = ""
    capabilities: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    endpoints: list[ServiceEndpoint] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_governance(self) -> ServiceDescriptor:
        self.service_name = self.service_name.strip()
        self.version = self.version.strip()
        self.environment = self.environment.strip()
        self.description = self.description.strip()

        if not self.service_name:
            raise ValueError("service_name must not be empty")

        if not self.version:
            raise ValueError("version must not be empty")

        if not self.environment:
            raise ValueError("environment must not be empty")

        for value in (self.service_name, self.version, self.environment):
            if any(character.isspace() for character in value):
                raise ValueError(
                    "service identity fields must not contain whitespace"
                )

        self.capabilities = sorted(
            {item.strip().upper() for item in self.capabilities if item.strip()}
        )
        self.permissions = sorted(
            {item.strip().upper() for item in self.permissions if item.strip()}
        )
        self.dependencies = sorted(
            {item.strip().upper() for item in self.dependencies if item.strip()}
        )

        for permission in self.permissions:
            if (
                self.plane in {ServicePlane.AI, ServicePlane.DATA_RESEARCH}
                and permission in AI_FORBIDDEN_PRIVILEGES
            ):
                raise ValueError(
                    f"AI/research plane may not hold privileged permission {permission}"
                )

            if permission in EXECUTION_PRIVILEGES and self.plane != ServicePlane.RISK:
                raise ValueError(
                    f"only RISK plane may hold execution permission {permission}"
                )

            if permission == "RISK_OVERRIDE" and self.plane != ServicePlane.RISK:
                raise ValueError("RISK_OVERRIDE is restricted to RISK plane")

            if permission == "KILL_SWITCH" and self.plane not in {
                ServicePlane.RISK,
                ServicePlane.CONTROL,
            }:
                raise ValueError(
                    "KILL_SWITCH is restricted to RISK or CONTROL plane"
                )

        resolved_service_id = (
            f"{self.environment}:{self.service_name}:{self.version}"
        )

        if self.service_id is None:
            self.service_id = resolved_service_id
        elif self.service_id != resolved_service_id:
            raise ValueError(
                "service_id must be deterministic and equal to "
                f"{resolved_service_id}"
            )

        return self

    def to_registration_payload(self) -> dict[str, object]:
        return {
            "service_id": self.service_id,
            "service_name": self.service_name,
            "version": self.version,
            "environment": self.environment,
            "plane": self.plane.value,
            "fail_closed_policy": self.fail_closed_policy.value,
            "description": self.description,
            "capabilities": self.capabilities,
            "permissions": self.permissions,
            "endpoints": [
                endpoint.model_dump(mode="json") for endpoint in self.endpoints
            ],
            "dependencies": self.dependencies,
        }