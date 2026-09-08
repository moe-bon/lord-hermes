//! The evaluator. Pure, deterministic, conformant to the shared fixture and
//! to the Python SDK. Precedence:
//!   lifecycle/targeting short-circuit -> fail_value
//!   then denylist (deny) > allowlist (allow) > type dispatch.

use crate::determinism::{bucket_for, select_bucketing_entity};
use crate::model::{CompiledFlag, EvaluationContext, FlagStatus, FlagType};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EvaluationOutcome {
    Enabled,
    Disabled,
    /// The flag could not be positively evaluated; use fail_value.
    UseFailValue(&'static str),
}

impl EvaluationOutcome {
    /// Resolve to a concrete boolean given the flag's declared fail_value.
    pub fn resolve(self, fail_value: bool) -> bool {
        match self {
            EvaluationOutcome::Enabled => true,
            EvaluationOutcome::Disabled => false,
            EvaluationOutcome::UseFailValue(_) => fail_value,
        }
    }

    pub fn reason(&self) -> &'static str {
        match self {
            EvaluationOutcome::Enabled => "enabled",
            EvaluationOutcome::Disabled => "disabled",
            EvaluationOutcome::UseFailValue(r) => r,
        }
    }
}

pub fn evaluate(
    flag: &CompiledFlag,
    ctx: &EvaluationContext,
    entity_priority: &[String],
    now_epoch_ms: u128,
) -> EvaluationOutcome {
    // --- Lifecycle short-circuits (all return fail_value) -------------------
    if flag.status == FlagStatus::Retired {
        // Evaluating a RETIRED flag means dead code is still live; the caller
        // must emit a warning metric (Binding Improvement #8).
        return EvaluationOutcome::UseFailValue("retired");
    }
    if flag.status == FlagStatus::Disabled {
        return EvaluationOutcome::UseFailValue("disabled");
    }
    if flag.status == FlagStatus::Draft {
        return EvaluationOutcome::UseFailValue("draft");
    }

    // --- Environment targeting ---------------------------------------------
    if !flag.environments.is_empty() && !flag.environments.contains(&ctx.environment) {
        return EvaluationOutcome::UseFailValue("environment_not_targeted");
    }

    // --- Expiry (anti-zombie) ----------------------------------------------
    if let Some(exp) = flag.expires_at_epoch_ms {
        if now_epoch_ms >= exp {
            return EvaluationOutcome::UseFailValue("expired");
        }
    }

    // --- Bucketing entity ---------------------------------------------------
    let entity = select_bucketing_entity(&ctx.attributes, entity_priority);

    // --- Denylist override: deny wins --------------------------------------
    if let Some(e) = entity {
        if flag.denylist.contains(e) {
            return EvaluationOutcome::Disabled;
        }
    }

    // --- Allowlist override: allow wins (short of deny) --------------------
    if let Some(e) = entity {
        if flag.allowlist.contains(e) {
            return EvaluationOutcome::Enabled;
        }
    }

    // --- Type dispatch ------------------------------------------------------
    match flag.flag_type {
        FlagType::Boolean => {
            if flag.bool_value {
                EvaluationOutcome::Enabled
            } else {
                EvaluationOutcome::Disabled
            }
        }
        FlagType::Allowlist => {
            // Only allowlisted entities are enabled (handled above); everyone
            // else is disabled.
            EvaluationOutcome::Disabled
        }
        FlagType::Denylist => {
            // Everyone except denylisted (handled above) is enabled.
            EvaluationOutcome::Enabled
        }
        FlagType::Percentage => {
            let Some(e) = entity else {
                // No stable entity -> cannot bucket safely -> fail_value.
                return EvaluationOutcome::UseFailValue("missing_bucketing_entity");
            };
            let bucket = bucket_for(&flag.flag_key, e);
            if bucket < flag.rollout_bps as u64 {
                EvaluationOutcome::Enabled
            } else {
                EvaluationOutcome::Disabled
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{FlagClass, FlagType};
    use std::collections::HashSet;

    fn base_flag(flag_type: FlagType) -> CompiledFlag {
        CompiledFlag {
            flag_key: "test.flag".to_string(),
            status: FlagStatus::Active,
            flag_type,
            flag_class: FlagClass::Standard,
            bool_value: true,
            rollout_bps: 5_000,
            allowlist: HashSet::new(),
            denylist: HashSet::new(),
            environments: HashSet::new(),
            fail_value: false,
            generation: 1,
            expires_at_epoch_ms: None,
        }
    }

    fn priority() -> Vec<String> {
        vec!["strategy_id", "service"]
            .into_iter()
            .map(String::from)
            .collect()
    }

    fn ctx_with_strategy(env: &str, strategy: &str) -> EvaluationContext {
        EvaluationContext {
            environment: env.to_string(),
            attributes: vec![
                ("strategy_id".to_string(), strategy.to_string()),
                ("service".to_string(), "exec-core".to_string()),
            ],
        }
    }

    #[test]
    fn retired_flag_uses_fail_value() {
        let mut f = base_flag(FlagType::Boolean);
        f.status = FlagStatus::Retired;
        f.fail_value = false;
        let ctx = ctx_with_strategy("production", "s1");
        let out = evaluate(&f, &ctx, &priority(), 0);
        assert_eq!(out, EvaluationOutcome::UseFailValue("retired"));
        assert!(!out.resolve(f.fail_value));
    }

    #[test]
    fn denylist_beats_allowlist_and_type() {
        let mut f = base_flag(FlagType::Boolean);
        f.bool_value = true;
        f.allowlist.insert("s1".to_string());
        f.denylist.insert("s1".to_string());
        let ctx = ctx_with_strategy("production", "s1");
        let out = evaluate(&f, &ctx, &priority(), 0);
        assert_eq!(out, EvaluationOutcome::Disabled, "deny must win");
    }

    #[test]
    fn percentage_without_entity_falls_back_to_fail_value() {
        let f = base_flag(FlagType::Percentage);
        let ctx = EvaluationContext {
            environment: "production".to_string(),
            attributes: vec![],
        };
        let out = evaluate(&f, &ctx, &priority(), 0);
        assert_eq!(out, EvaluationOutcome::UseFailValue("missing_bucketing_entity"));
    }

    #[test]
    fn environment_targeting_returns_fail_value() {
        let mut f = base_flag(FlagType::Boolean);
        f.environments.insert("paper".to_string());
        let ctx = ctx_with_strategy("production", "s1");
        let out = evaluate(&f, &ctx, &priority(), 0);
        assert_eq!(out, EvaluationOutcome::UseFailValue("environment_not_targeted"));
    }
}