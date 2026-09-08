"""Proof Test #1 (partial): Python side of the cross-language conformance gate.

The Rust side runs the same vectors via `cargo test -p apex-flag-engine`.
CI additionally generates 10,000 randomized vectors and diffs the verdicts
byte-for-byte, and checks bucket uniformity.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from apexquant_flags.determinism import DeterminismSpec, bucket_for
from apexquant_flags.evaluator import evaluate
from apexquant_flags.model import CompiledFlag, EvaluationContext, FlagClass, FlagStatus, FlagType

VECTORS_PATH = Path(__file__).resolve().parents[2] / "data/feature_flags/conformance_vectors.json"


def load_vectors() -> list[dict]:
    return json.loads(VECTORS_PATH.read_text(encoding="utf-8"))["vectors"]


def build_flag(vec: dict) -> CompiledFlag:
    return CompiledFlag(
        flag_key=vec["flag_key"],
        status=FlagStatus(vec["status"]),
        flag_type=FlagType(vec["flag_type"]),
        flag_class=FlagClass(vec["flag_class"]),
        bool_value=vec["bool_value"],
        rollout_bps=vec["rollout_bps"],
        allowlist=set(vec["allowlist"]),
        denylist=set(vec["denylist"]),
        environments=set(vec["environments"]),
        fail_value=vec["fail_value"],
        expires_at_epoch_ms=vec["expires_at_epoch_ms"],
    )


@pytest.mark.parametrize("vec", load_vectors(), ids=lambda v: v["flag_key"])
def test_python_evaluator_matches_expected(vec: dict) -> None:
    spec = DeterminismSpec.load()
    flag = build_flag(vec)
    ctx = EvaluationContext(
        environment=vec["context"]["environment"],
        attributes=[tuple(pair) for pair in vec["context"]["attributes"]],
    )

    outcome = evaluate(flag, ctx, spec.entity_priority, vec["now_epoch_ms"])
    enabled = outcome.resolve(flag.fail_value)

    assert enabled == vec["expected_enabled"], vec["flag_key"]
    assert outcome.reason == vec["expected_reason"], vec["flag_key"]


def test_bucket_uniformity() -> None:
    """Bucket distribution must be ~uniform over 10,000 entities."""
    buckets = [bucket_for("uniformity.flag", f"entity-{i}") for i in range(10_000)]

    # Every bucket is in range.
    assert all(0 <= b < 10_000 for b in buckets)

    # Chi-squared-style sanity: no decile should be wildly over/underfull.
    deciles = [0] * 10
    for b in buckets:
        deciles[b // 1000] += 1

    expected = 1000
    for count in deciles:
        assert abs(count - expected) < 200, f"bucket skew detected: {deciles}"