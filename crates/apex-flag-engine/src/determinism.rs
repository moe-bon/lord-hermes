//! Cross-language bucketing. Conforms EXACTLY to
//! data/feature_flags/determinism.yaml. The CI conformance job asserts the
//! embedded fixture matches the on-disk file and that Rust + Python produce
//! identical verdicts on the shared vectors.

use serde::Deserialize;
use xxhash_rust::xxh64::xxh64;

/// Embedded single-source-of-truth fixture (Binding Decision #2).
pub const DETERMINISM_YAML: &str =
    include_str!("../../../../data/feature_flags/determinism.yaml");

/// Fixed seed from the fixture. The conformance test asserts equality with
/// the parsed fixture value so the two can never silently diverge.
pub const SEED: u64 = 0x9E3779B97F4A7C15;

/// Basis-point modulus from the fixture.
pub const MODULUS: u64 = 10_000;

#[derive(Debug, Clone, Deserialize)]
pub struct DeterminismSpec {
    pub version: u32,
    pub hash: HashSpec,
    pub bucketing: BucketingSpec,
}

#[derive(Debug, Clone, Deserialize)]
pub struct HashSpec {
    pub algorithm: String,
    pub seed: String,
    pub encoding: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct BucketingSpec {
    pub modulus: u64,
    pub key_composition: String,
    pub entity_priority: Vec<String>,
}

impl DeterminismSpec {
    /// Parse the embedded fixture and assert it matches the compiled-in
    /// constants. This is the drift tripwire.
    pub fn load_and_verify() -> Self {
        let spec: DeterminismSpec = serde_yaml::from_str(DETERMINISM_YAML)
            .expect("determinism fixture must parse");

        assert_eq!(
            spec.bucketing.modulus, MODULUS,
            "fixture modulus drifted from compiled constant"
        );
        assert_eq!(
            spec.hash.algorithm, "xxhash64",
            "fixture hash algorithm drifted"
        );
        // seed in fixture is a hex string; verify it equals the constant.
        let fixture_seed = u64::from_str_radix(
            spec.hash.seed.trim_start_matches("0x"),
            16,
        )
        .expect("fixture seed must be hex");
        assert_eq!(fixture_seed, SEED, "fixture seed drifted from compiled constant");

        spec
    }

    pub fn entity_priority(&self) -> &[String] {
        &self.bucketing.entity_priority
    }
}

/// Select the single stable bucketing entity: the FIRST present attribute in
/// the priority order. Returns None if none is present — percentage flags then
/// fall back to fail_value (Binding Improvement #2: never bucket per-request).
pub fn select_bucketing_entity<'a>(
    attrs: &'a [(String, String)],
    priority: &[String],
) -> Option<&'a str> {
    for wanted in priority {
        for (key, value) in attrs {
            if key == wanted && !value.is_empty() {
                return Some(value.as_str());
            }
        }
    }
    None
}

/// Deterministic bucket in [0, MODULUS). Conforms to the fixture:
/// xxhash64(utf8("{flag_key}:{entity}"), seed) mod 10_000.
pub fn bucket_for(flag_key: &str, entity: &str) -> u64 {
    let input = format!("{}:{}", flag_key, entity);
    xxh64(input.as_bytes(), SEED) % MODULUS
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fixture_constants_are_consistent() {
        // Will panic if the embedded fixture drifts from the constants.
        let _ = DeterminismSpec::load_and_verify();
    }

    #[test]
    fn bucket_is_deterministic_and_in_range() {
        let a = bucket_for("live_trading_enabled", "strategy-42");
        let b = bucket_for("live_trading_enabled", "strategy-42");
        assert_eq!(a, b);
        assert!(a < MODULUS);
    }

    #[test]
    fn entity_selection_follows_priority() {
        let attrs = vec![
            ("service".to_string(), "exec-core".to_string()),
            ("strategy_id".to_string(), "strat-9".to_string()),
        ];
        let priority: Vec<String> =
            vec!["strategy_id", "model_id", "account_id", "service", "principal"]
                .into_iter().map(String::from).collect();

        assert_eq!(
            select_bucketing_entity(&attrs, &priority),
            Some("strat-9"),
            "strategy_id must win over service by priority"
        );
    }
}