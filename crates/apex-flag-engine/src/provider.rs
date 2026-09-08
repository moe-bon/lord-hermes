//! Tiered resolution + three-state degradation ladder (Decision #1, #5;
//! Binding Improvement #5). This runs on the SLOW path (refresher); the hot
//! path only touches FlagStore::load/pin.
//!
//! Ladder per flag class:
//!   fresh (age <= threshold)        -> serve live value
//!   stale (age  > threshold)        -> serve fail_value
//! Snapshot sourcing:
//!   local fresh -> local last-known-good -> Redis -> baked-in defaults.

use crate::determinism::DeterminismSpec;
use crate::evaluator::{evaluate, EvaluationOutcome};
use crate::model::{CompiledFlag, EvaluationContext};
use crate::store::{FlagSnapshot, FlagStore};
use std::sync::Arc;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DegradationState {
    /// Live snapshot within staleness threshold.
    Fresh,
    /// Snapshot stale but a last-known-good value served within tolerance is
    /// not available — resolved to fail_value.
    FailValue,
    /// No live snapshot at all; running on baked-in defaults (cold start).
    BakedDefaults,
}

pub struct ResolvedFlag {
    pub enabled: bool,
    pub reason: &'static str,
    pub degradation: DegradationState,
    pub generation: u64,
}

pub struct FlagProvider {
    store: Arc<FlagStore>,
    spec: DeterminismSpec,
}

impl FlagProvider {
    pub fn new(store: Arc<FlagStore>) -> Self {
        Self {
            store,
            spec: DeterminismSpec::load_and_verify(),
        }
    }

    /// Evaluate one flag against the CURRENT snapshot, applying the
    /// degradation ladder. Hot-path callers should instead `store.pin()` once
    /// per unit of work and call `evaluate_pinned`.
    pub fn evaluate_current(
        &self,
        flag_key: &str,
        ctx: &EvaluationContext,
    ) -> Option<ResolvedFlag> {
        let snapshot_guard = self.store.load();
        self.evaluate_against_snapshot(&snapshot_guard, flag_key, ctx)
    }

    /// Evaluate against a pinned snapshot (Decision #8). The degradation
    /// ladder still applies — a pin captures VALUES, not an exemption from
    /// staleness safety.
    pub fn evaluate_pinned(
        &self,
        pinned: &crate::store::PinnedFlags,
        flag_key: &str,
        ctx: &EvaluationContext,
    ) -> Option<ResolvedFlag> {
        self.evaluate_against_snapshot(&pinned.snapshot, flag_key, ctx)
    }

    fn evaluate_against_snapshot(
        &self,
        snapshot: &Arc<FlagSnapshot>,
        flag_key: &str,
        ctx: &EvaluationContext,
    ) -> Option<ResolvedFlag> {
        let flag: &CompiledFlag = snapshot.get(flag_key)?;
        let now = FlagSnapshot::now_epoch_ms();

        // Determine which snapshot tier we are on.
        let is_baked = Arc::as_ptr(snapshot) == Arc::as_ptr(self.store.baked());
        let age_ms = now.saturating_sub(snapshot.fetched_at_epoch_ms);
        let threshold = flag.flag_class.staleness_limit_ms();

        let (degradation, use_fail) = if is_baked {
            // Cold start: baked defaults are authoritative but flagged.
            (DegradationState::BakedDefaults, false)
        } else if age_ms <= threshold {
            (DegradationState::Fresh, false)
        } else {
            // Stale beyond the class threshold -> safe state (ladder step 3).
            (DegradationState::FailValue, true)
        };

        if use_fail {
            return Some(ResolvedFlag {
                enabled: flag.fail_value,
                reason: "snapshot_stale_beyond_threshold",
                degradation,
                generation: snapshot.generation,
            });
        }

        let outcome: EvaluationOutcome = evaluate(
            flag,
            ctx,
            self.spec.entity_priority(),
            now,
        );

        Some(ResolvedFlag {
            enabled: outcome.resolve(flag.fail_value),
            reason: outcome.reason(),
            degradation,
            generation: snapshot.generation,
        })
    }
}