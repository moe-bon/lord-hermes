from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class FlagStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    RETIRED = "RETIRED"


class FlagType(str, Enum):
    BOOLEAN = "BOOLEAN"
    PERCENTAGE = "PERCENTAGE"
    ALLOWLIST = "ALLOWLIST"
    DENYLIST = "DENYLIST"


class FlagClass(str, Enum):
    SAFETY_CRITICAL = "SAFETY_CRITICAL"
    TRADING_BEHAVIOR = "TRADING_BEHAVIOR"
    STANDARD = "STANDARD"

    @property
    def staleness_limit_ms(self) -> int:
        return {
            FlagClass.SAFETY_CRITICAL: 1_000,
            FlagClass.TRADING_BEHAVIOR: 5_000,
            FlagClass.STANDARD: 60_000,
        }[self]


class CompiledFlag(BaseModel):
    flag_key: str
    status: FlagStatus
    flag_type: FlagType
    flag_class: FlagClass = FlagClass.STANDARD

    bool_value: bool = False
    rollout_bps: int = Field(default=0, ge=0, le=10_000)
    allowlist: set[str] = Field(default_factory=set)
    denylist: set[str] = Field(default_factory=set)
    environments: set[str] = Field(default_factory=set)

    fail_value: bool = False

    generation: int = 1
    expires_at_epoch_ms: int | None = None


class EvaluationContext(BaseModel):
    environment: str = ""
    attributes: list[tuple[str, str]] = Field(default_factory=list)

    def attr(self, key: str) -> str | None:
        for k, v in self.attributes:
            if k == key:
                return v
        return None