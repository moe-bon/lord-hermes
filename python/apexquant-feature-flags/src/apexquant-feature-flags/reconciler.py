"""Redis<->Postgres reconciliation + anti-zombie sweep.

Runs every 30s (Binding Decision #6). Postgres is truth; Redis drift raises an
alert and is repaired from Postgres. Zombie detection (Binding Improvement #8):
a flag past review_at with zero recent evaluations is alerted and forced onto
the retirement path.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


SWEEP_INTERVAL_SECONDS = 30
# A flag with no evaluations in this window AND past review_at is a zombie.
ZOMBIE_EVAL_GAP_SECONDS = 7 * 24 * 3600


@dataclass
class ReconciliationReport:
    drift_flags: list[str]
    repaired: list[str]
    zombie_flags: list[str]
    forced_retirements: list[str]


class FlagReconciler:
    def __init__(self, repository, redis_client, alert_sink) -> None:
        self._repo = repository
        self._redis = redis_client
        self._alerts = alert_sink

    def run_once(self) -> ReconciliationReport:
        report = ReconciliationReport([], [], [], [])
        now = datetime.now(timezone.utc)

        # ---- Redis <-> Postgres drift --------------------------------------
        truth = self._repo.list_active_flags()
        for flag in truth:
            cached = self._redis_get(flag["flag_key"])
            if cached is None or cached.get("generation") != flag["generation"]:
                report.drift_flags.append(flag["flag_key"])
                self._redis_put(flag)
                report.repaired.append(flag["flag_key"])
                self._alerts.warn(
                    "flag_cache_drift",
                    flag_key=flag["flag_key"],
                    generation=flag["generation"],
                )

        # ---- Anti-zombie sweep ---------------------------------------------
        for flag in self._repo.list_flags_pending_review(now):
            last_eval = flag.get("last_evaluated_at")
            stale_eval = (
                last_eval is None
                or (now - last_eval).total_seconds() > ZOMBIE_EVAL_GAP_SECONDS
            )
            if flag["review_at"] <= now and stale_eval:
                report.zombie_flags.append(flag["flag_key"])
                self._alerts.critical(
                    "zombie_flag_forced_retirement",
                    flag_key=flag["flag_key"],
                    review_at=flag["review_at"].isoformat(),
                )
                self._repo.force_retire(flag["flag_key"])
                report.forced_retirements.append(flag["flag_key"])

        return report

    # -- Redis helpers (namespaced cache tier) -------------------------------
    def _redis_key(self, flag_key: str) -> str:
        return f"apex:flags:{flag_key}"

    def _redis_get(self, flag_key: str):
        import json

        raw = self._redis.get(self._redis_key(flag_key))
        if raw is None:
            return None
        return json.loads(raw)

    def _redis_put(self, flag: dict) -> None:
        import json

        self._redis.set(self._redis_key(flag["flag_key"]), json.dumps(flag))