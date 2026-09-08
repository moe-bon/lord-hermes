use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum SecretError {
    #[error("invalid secret reference: {0}")]
    InvalidReference(String),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum SecretClassification {
    Infrastructure,
    Database,
    Broker,
    Execution,
    Api,
    Model,
    Knowledge,
    Observability,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum SecretPlane {
    Control,
    MarketData,
    Trading,
    Risk,
    Ai,
    DataResearch,
    Observability,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum SecretAction {
    Read,
    Write,
    Rotate,
    Admin,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SecretScheme {
    Secret,
    Vault,
    Env,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SecretReference {
    pub scheme: SecretScheme,
    pub scope_or_path: String,
    pub key: Option<String>,
}

pub fn parse_secret_reference(value: &str) -> Result<SecretReference, SecretError> {
    let trimmed = value.trim();

    if let Some(rest) = trimmed.strip_prefix("secret://") {
        let mut parts = rest.splitn(2, '/');

        let scope = parts
            .next()
            .filter(|scope| !scope.is_empty())
            .ok_or_else(|| SecretError::InvalidReference(value.to_string()))?;

        let name = parts
            .next()
            .filter(|name| !name.is_empty())
            .ok_or_else(|| SecretError::InvalidReference(value.to_string()))?;

        return Ok(SecretReference {
            scheme: SecretScheme::Secret,
            scope_or_path: scope.to_string(),
            key: Some(name.to_string()),
        });
    }

    if let Some(rest) = trimmed.strip_prefix("vault://") {
        let mut parts = rest.splitn(2, '/');

        let path = parts
            .next()
            .filter(|path| !path.is_empty())
            .ok_or_else(|| SecretError::InvalidReference(value.to_string()))?;

        let key = parts.next().map(|key| key.to_string());

        return Ok(SecretReference {
            scheme: SecretScheme::Vault,
            scope_or_path: path.to_string(),
            key,
        });
    }

    if let Some(rest) = trimmed.strip_prefix("env://") {
        if rest.is_empty() {
            return Err(SecretError::InvalidReference(value.to_string()));
        }

        return Ok(SecretReference {
            scheme: SecretScheme::Env,
            scope_or_path: rest.to_string(),
            key: None,
        });
    }

    Err(SecretError::InvalidReference(value.to_string()))
}

pub fn is_secret_reference(value: &str) -> bool {
    parse_secret_reference(value).is_ok()
}

pub fn contains_secret_reference(value: &str) -> bool {
    value.contains("${") || value.contains("secret://") || value.contains("vault://")
}

const SECRET_KEY_MARKERS: &[&str] = &[
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "credential",
    "access_key",
];

pub fn is_secret_key(key: &str) -> bool {
    let normalized = key.to_ascii_lowercase();

    SECRET_KEY_MARKERS
        .iter()
        .any(|marker| normalized.contains(marker))
}

pub fn redact_if_secret(key: &str, value: &str) -> String {
    if is_secret_key(key) {
        "[REDACTED]".to_string()
    } else {
        value.to_string()
    }
}

pub fn evaluate_default_access(
    plane: SecretPlane,
    classification: SecretClassification,
    action: SecretAction,
) -> bool {
    if matches!(plane, SecretPlane::Ai | SecretPlane::DataResearch)
        && matches!(
            classification,
            SecretClassification::Broker
                | SecretClassification::Execution
                | SecretClassification::Database
                | SecretClassification::Infrastructure
        )
    {
        return false;
    }

    match plane {
        SecretPlane::Control => true,
        SecretPlane::Risk => matches!(
            action,
            SecretAction::Read
        ) && matches!(
            classification,
            SecretClassification::Broker
                | SecretClassification::Execution
                | SecretClassification::Database
                | SecretClassification::Infrastructure
                | SecretClassification::Api
                | SecretClassification::Observability
        ),
        SecretPlane::MarketData => {
            action == SecretAction::Read
                && matches!(
                    classification,
                    SecretClassification::Infrastructure
                        | SecretClassification::Database
                        | SecretClassification::Api
                        | SecretClassification::Observability
                )
        }
        SecretPlane::Trading => {
            action == SecretAction::Read
                && matches!(
                    classification,
                    SecretClassification::Database
                        | SecretClassification::Api
                        | SecretClassification::Observability
                )
        }
        SecretPlane::Ai => {
            action == SecretAction::Read
                && matches!(
                    classification,
                    SecretClassification::Model
                        | SecretClassification::Knowledge
                        | SecretClassification::Api
                        | SecretClassification::Observability
                )
        }
        SecretPlane::DataResearch => {
            action == SecretAction::Read
                && matches!(
                    classification,
                    SecretClassification::Model
                        | SecretClassification::Knowledge
                        | SecretClassification::Observability
                )
        }
        SecretPlane::Observability => {
            action == SecretAction::Read
                && matches!(
                    classification,
                    SecretClassification::Observability | SecretClassification::Infrastructure
                )
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_secret_reference() {
        let parsed = parse_secret_reference("secret://local/broker/api_key")
            .expect("secret reference should parse");

        assert_eq!(parsed.scheme, SecretScheme::Secret);
        assert_eq!(parsed.scope_or_path, "local");
        assert_eq!(parsed.key.as_deref(), Some("broker/api_key"));
    }

    #[test]
    fn parses_vault_reference() {
        let parsed = parse_secret_reference("vault://prod/postgres/password")
            .expect("vault reference should parse");

        assert_eq!(parsed.scheme, SecretScheme::Vault);
        assert_eq!(parsed.scope_or_path, "prod");
        assert_eq!(parsed.key.as_deref(), Some("postgres/password"));
    }

    #[test]
    fn rejects_plain_value() {
        assert!(parse_secret_reference("hunter2").is_err());
    }

    #[test]
    fn ai_cannot_read_broker_secret() {
        assert!(!evaluate_default_access(
            SecretPlane::Ai,
            SecretClassification::Broker,
            SecretAction::Read
        ));
    }

    #[test]
    fn risk_can_read_broker_secret() {
        assert!(evaluate_default_access(
            SecretPlane::Risk,
            SecretClassification::Broker,
            SecretAction::Read
        ));
    }

    #[test]
    fn redacts_secret_keys() {
        assert_eq!(redact_if_secret("BROKER_API_SECRET", "abc"), "[REDACTED]");
        assert_eq!(redact_if_secret("HOST", "localhost"), "localhost");
    }
}