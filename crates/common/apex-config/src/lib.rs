use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum ConfigError {
    #[error("missing configuration: {0}")]
    Missing(String),

    #[error("invalid configuration: {0}")]
    Invalid(String),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum EnvironmentName {
    Local,
    Sandbox,
    Paper,
    Shadow,
    Production,
}

impl EnvironmentName {
    pub fn parse(value: &str) -> Result<Self, ConfigError> {
        match value.trim().to_ascii_lowercase().as_str() {
            "local" => Ok(Self::Local),
            "sandbox" => Ok(Self::Sandbox),
            "paper" => Ok(Self::Paper),
            "shadow" => Ok(Self::Shadow),
            "production" => Ok(Self::Production),
            other => Err(ConfigError::Invalid(format!(
                "unknown environment {other}"
            ))),
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Local => "local",
            Self::Sandbox => "sandbox",
            Self::Paper => "paper",
            Self::Shadow => "shadow",
            Self::Production => "production",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum TradingMode {
    Development,
    Sandbox,
    Paper,
    Shadow,
    Production,
}

impl TradingMode {
    pub fn parse(value: &str) -> Result<Self, ConfigError> {
        match value.trim().to_ascii_uppercase().as_str() {
            "DEVELOPMENT" => Ok(Self::Development),
            "SANDBOX" => Ok(Self::Sandbox),
            "PAPER" => Ok(Self::Paper),
            "SHADOW" => Ok(Self::Shadow),
            "PRODUCTION" => Ok(Self::Production),
            other => Err(ConfigError::Invalid(format!(
                "unknown trading mode {other}"
            ))),
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Development => "DEVELOPMENT",
            Self::Sandbox => "SANDBOX",
            Self::Paper => "PAPER",
            Self::Shadow => "SHADOW",
            Self::Production => "PRODUCTION",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RuntimeEnvironmentInput {
    pub environment: String,
    pub trading_mode: Option<String>,
    pub live_capital_allowed: Option<String>,
    pub fail_closed_default: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RuntimeEnvironment {
    pub environment: EnvironmentName,
    pub trading_mode: TradingMode,
    pub live_capital_allowed: bool,
    pub fail_closed_default: bool,
}

impl RuntimeEnvironment {
    pub fn from_env() -> Result<Self, ConfigError> {
        let environment = std::env::var("APEX_ENVIRONMENT")
            .map_err(|_| ConfigError::Missing("APEX_ENVIRONMENT is required".into()))?;

        let trading_mode = std::env::var("APEX_TRADING_MODE").ok();
        let live_capital_allowed = std::env::var("APEX_LIVE_CAPITAL_ALLOWED").ok();
        let fail_closed_default = std::env::var("APEX_FAIL_CLOSED_DEFAULT").ok();

        Self::from_input(RuntimeEnvironmentInput {
            environment,
            trading_mode,
            live_capital_allowed,
            fail_closed_default,
        })
    }

    pub fn from_input(input: RuntimeEnvironmentInput) -> Result<Self, ConfigError> {
        let environment = EnvironmentName::parse(&input.environment)?;

        let expected_trading_mode = match environment {
            EnvironmentName::Local => TradingMode::Development,
            EnvironmentName::Sandbox => TradingMode::Sandbox,
            EnvironmentName::Paper => TradingMode::Paper,
            EnvironmentName::Shadow => TradingMode::Shadow,
            EnvironmentName::Production => TradingMode::Production,
        };

        let trading_mode = match input.trading_mode {
            Some(raw) => {
                let parsed = TradingMode::parse(&raw)?;

                if parsed != expected_trading_mode {
                    return Err(ConfigError::Invalid(format!(
                        "environment {} must use trading mode {}",
                        environment.as_str(),
                        expected_trading_mode.as_str()
                    )));
                }

                parsed
            }
            None => expected_trading_mode,
        };

        let live_capital_allowed = parse_bool(
            "APEX_LIVE_CAPITAL_ALLOWED",
            input.live_capital_allowed.as_deref(),
            false,
        )?;

        let fail_closed_default = parse_bool(
            "APEX_FAIL_CLOSED_DEFAULT",
            input.fail_closed_default.as_deref(),
            true,
        )?;

        if live_capital_allowed && environment != EnvironmentName::Production {
            return Err(ConfigError::Invalid(
                "live capital is only permitted in production".into(),
            ));
        }

        if !fail_closed_default
            && matches!(
                environment,
                EnvironmentName::Paper | EnvironmentName::Shadow | EnvironmentName::Production
            )
        {
            return Err(ConfigError::Invalid(
                "fail_closed_default must be true for critical environments".into(),
            ));
        }

        Ok(Self {
            environment,
            trading_mode,
            live_capital_allowed,
            fail_closed_default,
        })
    }
}

fn parse_bool(name: &str, raw: Option<&str>, default: bool) -> Result<bool, ConfigError> {
    let Some(raw) = raw else {
        return Ok(default);
    };

    let normalized = raw.trim().to_ascii_lowercase();

    match normalized.as_str() {
        "true" | "yes" | "1" => Ok(true),
        "false" | "no" | "0" => Ok(false),
        _ => Err(ConfigError::Invalid(format!(
            "{name} must be a boolean"
        ))),
    }
}

const SECRET_KEY_MARKERS: &[&str] = &[
    "password",
    "secret",
    "token",
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

pub fn redact_map(values: &HashMap<String, String>) -> HashMap<String, String> {
    values
        .iter()
        .map(|(key, value)| (key.clone(), redact_if_secret(key, value)))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn input(environment: &str, trading_mode: Option<&str>) -> RuntimeEnvironmentInput {
        RuntimeEnvironmentInput {
            environment: environment.to_string(),
            trading_mode: trading_mode.map(|value| value.to_string()),
            live_capital_allowed: Some("false".to_string()),
            fail_closed_default: Some("true".to_string()),
        }
    }

    #[test]
    fn local_defaults_to_development() {
        let env = RuntimeEnvironment::from_input(input("local", None))
            .expect("local environment should parse");

        assert_eq!(env.environment, EnvironmentName::Local);
        assert_eq!(env.trading_mode, TradingMode::Development);
        assert!(!env.live_capital_allowed);
        assert!(env.fail_closed_default);
    }

    #[test]
    fn rejects_wrong_trading_mode() {
        let result = RuntimeEnvironment::from_input(input("local", Some("PRODUCTION")));

        assert!(result.is_err());
    }

    #[test]
    fn rejects_live_capital_outside_production() {
        let mut env_input = input("paper", None);
        env_input.live_capital_allowed = Some("true".to_string());

        let result = RuntimeEnvironment::from_input(env_input);

        assert!(result.is_err());
    }

    #[test]
    fn rejects_fail_open_in_paper() {
        let mut env_input = input("paper", None);
        env_input.fail_closed_default = Some("false".to_string());

        let result = RuntimeEnvironment::from_input(env_input);

        assert!(result.is_err());
    }

    #[test]
    fn allows_production_with_live_capital_false() {
        let result = RuntimeEnvironment::from_input(input("production", None));

        assert!(result.is_ok());
    }

    #[test]
    fn redacts_secret_keys() {
        assert_eq!(redact_if_secret("BROKER_API_SECRET", "abc"), "[REDACTED]");
        assert_eq!(redact_if_secret("POSTGRES_PASSWORD", "abc"), "[REDACTED]");
        assert_eq!(redact_if_secret("HOST", "localhost"), "localhost");
    }
}