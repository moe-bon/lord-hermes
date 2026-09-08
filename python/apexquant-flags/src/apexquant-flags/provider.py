"""Tiered resolution + degradation ladder, conformant with the Rust provider.

This SDK provider is for control/research planes. The microsecond execution
path uses the Rust engine; verdicts are identical (CI-proven).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

from apexquant_flags.determinism import DeterminismSpec
from apexquant_flags.evaluator import evaluate
from apexquant_flags.model import CompiledFlag, EvaluationContext


class DegradationState(str, Enum):
    FRESH = "fresh"
    FAIL_VALUE = "fail_value"
    BAKED_DEFAULTS = "baked_defaults"


@dataclass
class ResolvedFlag:
    enabled: bool
    reason: str
    degradation: DegradationState
    generation: int


@dataclass
class Snapshot:
    generation: int
    fetched_at_epoch_ms: int
    flags: dict[str, CompiledFlag]


class FlagProvider:
    def __init__(self, baked: Snapshot) -> None:
        self._spec = DeterminismSpec.load()
        self._baked = baked
        self._current: Snapshot = baked

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    def refresh(self, snapshot: Snapshot) -> None:
        self._current = snapshot

    def pin(self) -> Snapshot:
        # Units of work capture this snapshot; flips afterwards do not affect it.
        return self._current

    def evaluate(
        self,
        flag_key: str,
        ctx: EvaluationContext,
        snapshot: Snapshot | None = None,
    ) -> ResolvedFlag | None:
        snap = snapshot or self._current
        flag = snap.flags.get(flag_key)
        if flag is None:
            return None

        now = self._now_ms()
        is_baked = snap is self._baked
        age_ms = max(0, now - snap.fetched_at_epoch_ms)
        threshold = flag.flag_class.staleness_limit_ms

        if is_baked:
            degradation = DegradationState.BAKED_DEFAULTS
            use_fail = False
        elif age_ms <= threshold:
            degradation = DegradationState.FRESH
            use_fail = False
        else:
            degradation = DegradationState.FAIL_VALUE
            use_fail = True

        if use_fail:
            return ResolvedFlag(
                enabled=flag.fail_value,
                reason="snapshot_stale_beyond_threshold",
                degradation=degradation,
                generation=snap.generation,
            )

        outcome = evaluate(flag, ctx, self._spec.entity_priority, now)
        return ResolvedFlag(
            enabled=outcome.resolve(flag.fail_value),
            reason=outcome.reason,
            degradation=degradation,
            generation=snap.generation,
        )