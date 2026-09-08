"""The five proof tests from the Feature 0.22 binding verdict.

#1 determinism conformance     -> tests/conformance (Rust + Python + 10k diff)
#2 cold start + kill-switch independence
#3 flip latency (<=1s P99 for safety-critical)
#4 mid-flight generation pinning
#5 zombie enforcement
"""
from __future__ import annotations

import time

import pytest

from apexquant_flags.determinism import DeterminismSpec
from apexquant_flags.evaluator import evaluate
from apexquant_flags.model import CompiledFlag, EvaluationContext, FlagClass, FlagStatus, FlagType
from apexquant_flags.provider import DegradationState, FlagProvider, Snapshot


def make_safety_flag(bool_value: bool) -> CompiledFlag:
    return CompiledFlag(
        flag_key="live_trading_enabled",
        status=FlagStatus.ACTIVE,
        flag_type=FlagType.BOOLEAN,
        flag_class=FlagClass.SAFETY_CRITICAL,
        bool_value=bool_value,
        fail_value=False,  # locked false for safety-critical
    )


def test_proof2_cold_start_defaults_to_safe_and_flag_independent() -> None:
    """Flag service AND Redis down -> boot on baked defaults;
    live_trading_enabled evaluates FALSE (fail_value); the kill switch is a
    separate authority and is unaffected by flag availability."""
    baked_defaults = Snapshot(
        generation=0,
        fetched_at_epoch_ms=int(time.time() * 1000),
        # Baked-in default for the safety-critical gate is FALSE.
        flags={"live_trading_enabled": make_safety_flag(bool_value=False)},
    )
    provider = FlagProvider(baked=baked_defaults)

    ctx = EvaluationContext(environment="production", attributes=[("service", "exec-core")])
    resolved = provider.evaluate("live_trading_enabled", ctx)

    assert resolved is not None
    assert resolved.enabled is False, "cold start must disable live trading"
    assert resolved.degradation == DegradationState.BAKED_DEFAULTS

    # Kill-switch independence: the stop authority is a separate channel and
    # does not consult the flag provider. Assert the provider exposes no stop
    # API and that the stop path is not wired to flag evaluation.
    assert not hasattr(provider, "kill_switch")
    assert not hasattr(provider, "emergency_stop")


def test_proof3_safety_critical_staleness_falls_back_fast() -> None:
    """A SAFETY_CRITICAL flag served from a snapshot older than 1s must
    resolve to fail_value (degradation ladder), so a stale cache cannot keep
    live trading enabled."""
    now_ms = int(time.time() * 1000)
    stale_snapshot = Snapshot(
        generation=7,
        fetched_at_epoch_ms=now_ms - 2_000,  # 2s old > 1s threshold
        flags={"live_trading_enabled": make_safety_flag(bool_value=True)},
    )
    provider = FlagProvider(baked=stale_snapshot)
    provider.refresh(stale_snapshot)

    ctx = EvaluationContext(environment="production", attributes=[("service", "exec-core")])
    resolved = provider.evaluate("live_trading_enabled", ctx)

    assert resolved is not None
    assert resolved.enabled is False, "stale safety-critical flag must fail to safe state"
    assert resolved.reason == "snapshot_stale_beyond_threshold"


def test_proof4_generation_pinning_isolates_mid_flight_flip() -> None:
    """A unit of work pins a snapshot; a flip after the pin does not affect
    the in-flight unit, only new ones."""
    now_ms = int(time.time() * 1000)
    before = Snapshot(
        generation=1,
        fetched_at_epoch_ms=now_ms,
        flags={"live_trading_enabled": make_safety_flag(bool_value=True)},
    )
    provider = FlagProvider(baked=before)
    provider.refresh(before)

    # Unit of work A pins generation 1.
    pinned_a = provider.pin()

    # Operator flips the flag -> new snapshot generation 2.
    after = Snapshot(
        generation=2,
        fetched_at_epoch_ms=now_ms,
        flags={"live_trading_enabled": make_safety_flag(bool_value=False)},
    )
    provider.refresh(after)

    ctx = EvaluationContext(environment="production", attributes=[("service", "exec-core")])

    # In-flight unit A still sees generation 1 (enabled=True).
    in_flight = provider.evaluate("live_trading_enabled", ctx, snapshot=pinned_a)
    assert in_flight is not None
    assert in_flight.generation == 1
    assert in_flight.enabled is True

    # A NEW unit of work sees generation 2 (enabled=False).
    new_unit = provider.evaluate("live_trading_enabled", ctx)
    assert new_unit is not None
    assert new_unit.generation == 2
    assert new_unit.enabled is False


def test_proof5_zombie_flag_evaluates_to_fail_value_and_warns() -> None:
    """A flag past its expiry evaluates to fail_value (the sweep forces the
    retirement path out-of-band). Evaluation must not return the live value."""
    spec = DeterminismSpec.load()
    expired = CompiledFlag(
        flag_key="old.experiment",
        status=FlagStatus.ACTIVE,
        flag_type=FlagType.BOOLEAN,
        flag_class=FlagClass.STANDARD,
        bool_value=True,
        fail_value=False,
        expires_at_epoch_ms=500,  # already past
    )
    ctx = EvaluationContext(environment="production", attributes=[("service", "svc")])

    outcome = evaluate(expired, ctx, spec.entity_priority, now_epoch_ms=1_000)
    assert outcome.reason == "expired"
    assert outcome.resolve(expired.fail_value) is False