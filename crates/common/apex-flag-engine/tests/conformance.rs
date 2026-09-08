//! Rust side of the cross-language conformance gate. Runs the SAME vectors as
//! the Python test. CI asserts Rust + Python verdicts are byte-identical.

use apex_flag_engine::determinism::DeterminismSpec;
use apex_flag_engine::evaluator::evaluate;
use apex_flag_engine::model::{
    CompiledFlag, EvaluationContext, FlagClass, FlagStatus, FlagType,
};
use serde::Deserialize;
use std::collections::HashSet;

#[derive(Deserialize)]
struct VectorFile {
    vectors: Vec<Vector>,
}

#[derive(Deserialize)]
struct Vector {
    flag_key: String,
    status: String,
    flag_type: String,
    flag_class: String,
    bool_value: bool,
    rollout_bps: u32,
    allowlist: Vec<String>,
    denylist: Vec<String>,
    environments: Vec<String>,
    fail_value: bool,
    expires_at_epoch_ms: Option<u128>,
    context: VectorContext,
    now_epoch_ms: u128,
    expected_enabled: bool,
    expected_reason: String,
}

#[derive(Deserialize)]
struct VectorContext {
    environment: String,
    attributes: Vec<(String, String)>,
}

fn parse_status(s: &str) -> FlagStatus {
    match s {
        "DRAFT" => FlagStatus::Draft,
        "ACTIVE" => FlagStatus::Active,
        "DISABLED" => FlagStatus::Disabled,
        "RETIRED" => FlagStatus::Retired,
        other => panic!("unknown status {other}"),
    }
}

fn parse_type(s: &str) -> FlagType {
    match s {
        "BOOLEAN" => FlagType::Boolean,
        "PERCENTAGE" => FlagType::Percentage,
        "ALLOWLIST" => FlagType::Allowlist,
        "DENYLIST" => FlagType::Denylist,
        other => panic!("unknown type {other}"),
    }
}

fn parse_class(s: &str) -> FlagClass {
    match s {
        "SAFETY_CRITICAL" => FlagClass::SafetyCritical,
        "TRADING_BEHAVIOR" => FlagClass::TradingBehavior,
        "STANDARD" => FlagClass::Standard,
        other => panic!("unknown class {other}"),
    }
}

#[test]
fn rust_evaluator_matches_expected_vectors() {
    let spec = DeterminismSpec::load_and_verify();

    let raw = include_str!("../../../../data/feature_flags/conformance_vectors.json");
    let file: VectorFile = serde_json::from_str(raw).expect("vectors must parse");

    for vec in &file.vectors {
        let flag = CompiledFlag {
            flag_key: vec.flag_key.clone(),
            status: parse_status(&vec.status),
            flag_type: parse_type(&vec.flag_type),
            flag_class: parse_class(&vec.flag_class),
            bool_value: vec.bool_value,
            rollout_bps: vec.rollout_bps,
            allowlist: vec.allowlist.iter().cloned().collect::<HashSet<_>>(),
            denylist: vec.denylist.iter().cloned().collect::<HashSet<_>>(),
            environments: vec.environments.iter().cloned().collect::<HashSet<_>>(),
            fail_value: vec.fail_value,
            generation: 1,
            expires_at_epoch_ms: vec.expires_at_epoch_ms,
        };

        let ctx = EvaluationContext {
            environment: vec.context.environment.clone(),
            attributes: vec.context.attributes.clone(),
        };

        let outcome = evaluate(&flag, &ctx, spec.entity_priority(), vec.now_epoch_ms);
        let enabled = outcome.resolve(flag.fail_value);

        assert_eq!(
            enabled, vec.expected_enabled,
            "verdict mismatch for {}",
            vec.flag_key
        );
        assert_eq!(
            outcome.reason(),
            vec.expected_reason,
            "reason mismatch for {}",
            vec.flag_key
        );
    }
}