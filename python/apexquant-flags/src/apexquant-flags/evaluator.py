"""The evaluator. Byte-for-byte conformant with apex-flag-engine (Rust).

Precedence: lifecycle/targeting short-circuit -> fail_value, then
denylist (deny) > allowlist (allow) > type dispatch.
"""
from __future__ import annotations

from dataclasses import dataclass

from apexquant_flags.determinism import bucket_for, select_bucketing_entity
from apexquant_flags.model import CompiledFlag, EvaluationContext, FlagStatus, FlagType


@dataclass(frozen=True)
class EvaluationOutcome:
    kind: str            # "enabled" | "disabled" | "fail_value"
    reason: str

    def resolve(self, fail_value: bool) -> bool:
        if self.kind == "enabled":
            return True
        if self.kind == "disabled":
            return False
        return fail_value


def _fail(reason: str) -> EvaluationOutcome:
    return EvaluationOutcome(kind="fail_value", reason=reason)


def evaluate(
    flag: CompiledFlag,
    ctx: EvaluationContext,
    entity_priority: list[str],
    now_epoch_ms: int,
) -> EvaluationOutcome:
    # --- Lifecycle short-circuits ------------------------------------------
    if flag.status == FlagStatus.RETIRED:
        return _fail("retired")
    if flag.status == FlagStatus.DISABLED:
        return _fail("disabled")
    if flag.status == FlagStatus.DRAFT:
        return _fail("draft")

    # --- Environment targeting ---------------------------------------------
    if flag.environments and ctx.environment not in flag.environments:
        return _fail("environment_not_targeted")

    # --- Expiry (anti-zombie) ----------------------------------------------
    if flag.expires_at_epoch_ms is not None and now_epoch_ms >= flag.expires_at_epoch_ms:
        return _fail("expired")

    # --- Bucketing entity ---------------------------------------------------
    entity = select_bucketing_entity(ctx.attributes, entity_priority)

    # --- Denylist override: deny wins --------------------------------------
    if entity is not None and entity in flag.denylist:
        return EvaluationOutcome(kind="disabled", reason="denylisted")

    # --- Allowlist override -------------------------------------------------
    if entity is not None and entity in flag.allowlist:
        return EvaluationOutcome(kind="enabled", reason="allowlisted")

    # --- Type dispatch ------------------------------------------------------
    if flag.flag_type == FlagType.BOOLEAN:
        return (
            EvaluationOutcome(kind="enabled", reason="boolean")
            if flag.bool_value
            else EvaluationOutcome(kind="disabled", reason="boolean")
        )

    if flag.flag_type == FlagType.ALLOWLIST:
        return EvaluationOutcome(kind="disabled", reason="not_in_allowlist")

    if flag.flag_type == FlagType.DENYLIST:
        return EvaluationOutcome(kind="enabled", reason="not_in_denylist")

    if flag.flag_type == FlagType.PERCENTAGE:
        if entity is None:
            return _fail("missing_bucketing_entity")
        bucket = bucket_for(flag.flag_key, entity)
        if bucket < flag.rollout_bps:
            return EvaluationOutcome(kind="enabled", reason="percentage")
        return EvaluationOutcome(kind="disabled", reason="percentage")

    return _fail("unknown_type")