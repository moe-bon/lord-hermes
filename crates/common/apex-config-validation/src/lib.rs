use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashMap};
use thiserror::Error;

pub const VALIDATION_POLICY_YAML: &str =
    include_str!("../../../../data/config/validation_policy.yaml");

#[derive(Debug, Error)]
pub enum ConfigValidationError {
    #[error("policy error: {0}")]
    Policy(String),

    #[error("parse error: {0}")]
    Parse(String),

    #[error("validation failed")]
    ValidationFailed,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ValidationPolicy {
    pub version: u32,
    pub secret_key_markers: Vec<String>,
    pub allowed_secret_reference_prefixes: Vec<String>,
    pub environments: Vec<String>,
    pub planes: Vec<String>,
    pub fail_closed_policies: Vec<String>,
    pub trading_mode_by_environment: HashMap<String, String>,
    pub require_fail_closed_for: Vec<String>,
}

impl ValidationPolicy {
    pub fn load_embedded() -> Result<Self, ConfigValidationError> {
        serde_yaml::from_str(VALIDATION_POLICY_YAML)
            .map_err(|e| ConfigValidationError::Policy(e.to_string()))
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum Severity {
    ERROR,
    WARNING,
}

#[derive(Debug, Clone, Serialize)]
pub struct ValidationIssue {
    pub severity: Severity,
    pub path: String,
    pub message: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ValidationReport {
    pub schema_key: String,
    pub ok: bool,
    pub config_hash: String,
    pub errors: Vec<ValidationIssue>,
    pub warnings: Vec<ValidationIssue>,
}

pub fn parse_yaml_to_json(text: &str) -> Result<Value, ConfigValidationError> {
    let yaml_value: serde_yaml::Value =
        serde_yaml::from_str(text).map_err(|e| ConfigValidationError::Parse(e.to_string()))?;

    serde_json::to_value(yaml_value).map_err(|e| ConfigValidationError::Parse(e.to_string()))
}

pub fn canonicalize(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let mut sorted: BTreeMap<String, Value> = BTreeMap::new();

            for (key, val) in map {
                sorted.insert(key.clone(), canonicalize(val));
            }

            let mut out = Map::new();

            for (key, val) in sorted {
                out.insert(key, val);
            }

            Value::Object(out)
        }
        Value::Array(items) => Value::Array(items.iter().map(canonicalize).collect()),
        other => other.clone(),
    }
}

pub fn hash_config(value: &Value) -> String {
    let canonical = canonicalize(value);
    let serialized = serde_json::to_string(&canonical).expect("canonical JSON must serialize");

    let mut hasher = Sha256::new();
    hasher.update(serialized.as_bytes());

    hex::encode(hasher.finalize())
}

fn is_secret_key(key: &str, policy: &ValidationPolicy) -> bool {
    let normalized = key.to_lowercase();

    policy
        .secret_key_markers
        .iter()
        .any(|marker| normalized.contains(marker))
}

fn is_secret_reference(value: &Value, policy: &ValidationPolicy) -> bool {
    let Some(text) = value.as_str() else {
        return false;
    };

    if text.starts_with("${") && text.ends_with('}') {
        return true;
    }

    policy
        .allowed_secret_reference_prefixes
        .iter()
        .any(|prefix| text.starts_with(prefix))
}

pub fn scan_secrets(
    value: &Value,
    policy: &ValidationPolicy,
    path: &str,
) -> Vec<ValidationIssue> {
    let mut issues = Vec::new();

    match value {
        Value::Object(map) => {
            for (key, item) in map {
                let key_path = format!("{}.{}", path, key);

                if is_secret_key(key, policy) {
                    if item.is_string() && !is_secret_reference(item, policy) {
                        issues.push(ValidationIssue {
                            severity: Severity::ERROR,
                            path: key_path.clone(),
                            message:
                                "literal secret detected; use env://, vault://, secret://, or ${VAR} references only"
                                    .to_string(),
                        });
                        continue;
                    }
                }

                issues.extend(scan_secrets(item, policy, &key_path));
            }
        }
        Value::Array(items) => {
            for (index, item) in items.iter().enumerate() {
                let item_path = format!("{}[{}]", path, index);
                issues.extend(scan_secrets(item, policy, &item_path));
            }
        }
        _ => {}
    }

    issues
}

fn get_str<'a>(value: &'a Value, key: &str) -> Option<&'a str> {
    value.get(key).and_then(|v| v.as_str())
}

fn get_bool(value: &Value, key: &str) -> Option<bool> {
    value.get(key).and_then(|v| v.as_bool())
}

fn error(path: &str, message: &str) -> ValidationIssue {
    ValidationIssue {
        severity: Severity::ERROR,
        path: path.to_string(),
        message: message.to_string(),
    }
}

pub fn validate_service_manifest(value: &Value) -> Result<ValidationReport, ConfigValidationError> {
    let policy = ValidationPolicy::load_embedded()?;
    let mut errors = Vec::new();

    let schema_version = get_str(value, "schema_version").unwrap_or_default();
    if schema_version != "service_manifest/v1" {
        errors.push(error(
            "$.schema_version",
            "schema_version must be service_manifest/v1",
        ));
    }

    let environment = get_str(value, "environment").unwrap_or_default();
    if !policy.environments.iter().any(|e| e == environment) {
        errors.push(error("$.environment", "environment is not allowed"));
    }

    let plane = get_str(value, "plane").unwrap_or_default();
    if !policy.planes.iter().any(|p| p == plane) {
        errors.push(error("$.plane", "plane is not allowed"));
    }

    let fail_closed_policy = get_str(value, "fail_closed_policy").unwrap_or_default();
    if !policy
        .fail_closed_policies
        .iter()
        .any(|f| f == fail_closed_policy)
    {
        errors.push(error(
            "$.fail_closed_policy",
            "fail_closed_policy is not allowed",
        ));
    }

    let live_trading_allowed = get_bool(value, "live_trading_allowed").unwrap_or(false);
    if live_trading_allowed && environment != "production" {
        errors.push(error(
            "$.live_trading_allowed",
            "live_trading_allowed may only be true in production",
        ));
    }

    errors.extend(scan_secrets(value, &policy, "$"));

    let config_hash = hash_config(value);

    Ok(ValidationReport {
        schema_key: "service_manifest/v1".to_string(),
        ok: errors.is_empty(),
        config_hash,
        errors,
        warnings: Vec::new(),
    })
}

pub fn validate_environment_manifest(
    value: &Value,
) -> Result<ValidationReport, ConfigValidationError> {
    let policy = ValidationPolicy::load_embedded()?;
    let mut errors = Vec::new();

    let schema_version = get_str(value, "schema_version").unwrap_or_default();
    if schema_version != "environment_manifest/v1" {
        errors.push(error(
            "$.schema_version",
            "schema_version must be environment_manifest/v1",
        ));
    }

    let environment = get_str(value, "environment").unwrap_or_default();
    if !policy.environments.iter().any(|e| e == environment) {
        errors.push(error("$.environment", "environment is not allowed"));
    }

    let trading_mode = get_str(value, "trading_mode").unwrap_or_default();
    if let Some(expected) = policy.trading_mode_by_environment.get(environment) {
        if trading_mode != expected {
            errors.push(error(
                "$.trading_mode",
                &format!("environment {environment} must use trading mode {expected}"),
            ));
        }
    }

    let live_capital_allowed = get_bool(value, "live_capital_allowed").unwrap_or(false);
    if live_capital_allowed && environment != "production" {
        errors.push(error(
            "$.live_capital_allowed",
            "live_capital_allowed may only be true in production",
        ));
    }

    let fail_closed_default = get_bool(value, "fail_closed_default").unwrap_or(false);
    if policy
        .require_fail_closed_for
        .iter()
        .any(|e| e == environment)
        && !fail_closed_default
    {
        errors.push(error(
            "$.fail_closed_default",
            &format!("environment {environment} must have fail_closed_default=true"),
        ));
    }

    let observability_required = get_bool(value, "observability_required").unwrap_or(true);
    if !observability_required {
        errors.push(error(
            "$.observability_required",
            "observability_required must be true",
        ));
    }

    if value
        .get("infrastructure")
        .and_then(|v| v.as_object())
        .is_none()
    {
        errors.push(error(
            "$.infrastructure",
            "infrastructure must be an object with at least one entry",
        ));
    }

    errors.extend(scan_secrets(value, &policy, "$"));

    let config_hash = hash_config(value);

    Ok(ValidationReport {
        schema_key: "environment_manifest/v1".to_string(),
        ok: errors.is_empty(),
        config_hash,
        errors,
        warnings: Vec::new(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_service_manifest() -> &'static str {
        r#"
schema_version: service_manifest/v1
service_name: execution-core
service_version: 0.1.0
environment: local
plane: TRADING
fail_closed_policy: SHUTDOWN
live_trading_allowed: false
dependencies:
  - postgres
endpoints:
  http: http://execution-core:8080
resources:
  cpus: "1.0"
  memory: 512M
"#
    }

    fn valid_environment_manifest() -> &'static str {
        r#"
schema_version: environment_manifest/v1
environment: local
trading_mode: DEVELOPMENT
live_capital_allowed: false
fail_closed_default: true
observability_required: true
infrastructure:
  postgres:
    host: postgres
    port: 5432
    user: env://POSTGRES_USER
    password: env://POSTGRES_PASSWORD
"#
    }

    #[test]
    fn valid_service_manifest_passes() {
        let value = parse_yaml_to_json(valid_service_manifest()).unwrap();
        let report = validate_service_manifest(&value).unwrap();

        assert!(report.ok, "{:?}", report.errors);
    }

    #[test]
    fn valid_environment_manifest_passes() {
        let value = parse_yaml_to_json(valid_environment_manifest()).unwrap();
        let report = validate_environment_manifest(&value).unwrap();

        assert!(report.ok, "{:?}", report.errors);
    }

    #[test]
    fn literal_secret_is_rejected() {
        let yaml = r#"
schema_version: service_manifest/v1
service_name: execution-core
service_version: 0.1.0
environment: local
plane: TRADING
fail_closed_policy: SHUTDOWN
live_trading_allowed: false
credentials:
  broker_password: hunter2
"#;

        let value = parse_yaml_to_json(yaml).unwrap();
        let report = validate_service_manifest(&value).unwrap();

        assert!(!report.ok);
        assert!(report
            .errors
            .iter()
            .any(|e| e.path == "$.credentials.broker_password"));
    }

    #[test]
    fn live_trading_only_allowed_in_production() {
        let yaml = r#"
schema_version: service_manifest/v1
service_name: execution-core
service_version: 0.1.0
environment: local
plane: TRADING
fail_closed_policy: SHUTDOWN
live_trading_allowed: true
"#;

        let value = parse_yaml_to_json(yaml).unwrap();
        let report = validate_service_manifest(&value).unwrap();

        assert!(!report.ok);
    }

    #[test]
    fn environment_trading_mode_mismatch_is_rejected() {
        let yaml = r#"
schema_version: environment_manifest/v1
environment: local
trading_mode: PRODUCTION
live_capital_allowed: false
fail_closed_default: true
observability_required: true
infrastructure:
  postgres:
    host: postgres
"#;

        let value = parse_yaml_to_json(yaml).unwrap();
        let report = validate_environment_manifest(&value).unwrap();

        assert!(!report.ok);
    }

    #[test]
    fn canonical_hash_is_stable_regardless_of_key_order() {
        let a = serde_json::json!({
            "b": 1,
            "a": {
                "y": true,
                "x": "value"
            }
        });

        let b = serde_json::json!({
            "a": {
                "x": "value",
                "y": true
            },
            "b": 1
        });

        assert_eq!(hash_config(&a), hash_config(&b));
    }
}