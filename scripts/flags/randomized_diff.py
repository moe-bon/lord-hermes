"""Generate 10,000 randomized (flag, context) vectors, evaluate them in Python,
and write a verdict file that the Rust harness re-evaluates and diffs.

In CI the Rust harness (apex-flag-engine::fuzz_diff) reads the same vectors,
produces its own verdicts, and the two files are diffed byte-for-byte. Any
divergence fails the build.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from apexquant_flags.determinism import DeterminismSpec, bucket_for
from apexquant_flags.evaluator import evaluate
from apexquant_flags.model import CompiledFlag, EvaluationContext, FlagClass, FlagStatus, FlagType

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "test-results/flags/conformance-random.json"


def main() -> None:
    rng = random.Random(0xAPEX := 0xA9E7)  # fixed seed -> reproducible
    spec = DeterminismSpec.load()

    statuses = [FlagStatus.ACTIVE, FlagStatus.DISABLED, FlagStatus.RETIRED]
    types = [FlagType.BOOLEAN, FlagType.PERCENTAGE, FlagType.ALLOWLIST, FlagType.DENYLIST]
    classes = [FlagClass.SAFETY_CRITICAL, FlagClass.TRADING_BEHAVIOR, FlagClass.STANDARD]

    vectors = []
    for i in range(10_000):
        flag_type = rng.choice(types)
        flag = CompiledFlag(
            flag_key=f"rand.flag.{i % 97}",
            status=rng.choice(statuses),
            flag_type=flag_type,
            flag_class=rng.choice(classes),
            bool_value=rng.random() > 0.5,
            rollout_bps=rng.randint(0, 10_000),
            allowlist={f"ent-{rng.randint(0, 50)}"},
            denylist={f"ent-{rng.randint(0, 50)}"},
            environments=set(),
            fail_value=rng.random() > 0.5,
            expires_at_epoch_ms=None,
        )
        entity = f"ent-{rng.randint(0, 60)}"
        ctx = EvaluationContext(
            environment="production",
            attributes=[("strategy_id", entity), ("service", "exec-core")],
        )
        outcome = evaluate(flag, ctx, spec.entity_priority, 1_000)
        vectors.append(
            {
                "flag": flag.model_dump(mode="json"),
                "context": ctx.model_dump(),
                "now_epoch_ms": 1_000,
                "python_enabled": outcome.resolve(flag.fail_value),
                "python_reason": outcome.reason,
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"vectors": vectors}, sort_keys=True), encoding="utf-8")
    print(f"wrote {len(vectors)} randomized vectors -> {OUT}")


if __name__ == "__main__":
    main()