use serde::{Deserialize, Serialize};
use std::collections::HashSet;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum FlagStatus {
    Draft,
    Active,
    Disabled,
    Retired,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum FlagType {
    Boolean,
    Percentage,
    Allowlist,
    Denylist,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum FlagClass {
    /// fail_value locked false; staleness threshold 1s.
    SafetyCritical,
    /// Strategy/model gates; staleness threshold 5s.
    TradingBehavior,
    /// Everything else; staleness threshold 60s.
    Standard,
}

impl FlagClass {
    /// Degradation ladder threshold (Binding Improvement #5).
    pub fn staleness_limit_ms(&self) -> u128 {
        match self {
            FlagClass::SafetyCritical => 1_000,
            FlagClass::TradingBehavior => 5_000,
            FlagClass::Standard => 60_000,
        }
    }
}

/// A flag compiled for evaluation. Immutable once in a snapshot.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompiledFlag {
    pub flag_key: String,
    pub status: FlagStatus,
    pub flag_type: FlagType,
    pub flag_class: FlagClass,

    pub bool_value: bool,
    pub rollout_bps: u32,
    pub allowlist: HashSet<String>,
    pub denylist: HashSet<String>,
    /// Empty = all environments.
    pub environments: HashSet<String>,

    /// The safe state returned on any failure / non-target / staleness.
    pub fail_value: bool,

    pub generation: u64,
    pub expires_at_epoch_ms: Option<u128>,
}

/// Evaluation context. Attributes drive targeting + bucketing.
#[derive(Debug, Clone, Default)]
pub struct EvaluationContext {
    pub environment: String,
    /// Stable attributes: service, plane, strategy_id, model_id,
    /// account_id, principal, ...
    pub attributes: Vec<(String, String)>,
}

impl EvaluationContext {
    pub fn attr(&self, key: &str) -> Option<&str> {
        self.attributes
            .iter()
            .find(|(k, _)| k == key)
            .map(|(_, v)| v.as_str())
    }
}