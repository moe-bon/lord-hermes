use crate::errors::GatewayError;
use apex_auth::decode_secret_b64;
use std::net::SocketAddr;
use url::Url;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AuthMode {
    Disabled,
    Permissive,
    Enforced,
}

#[derive(Debug, Clone)]
pub struct Upstream {
    pub service_name: String,
    pub plane: String,
    pub base_url: Url,
}

#[derive(Debug, Clone)]
pub struct Config {
    pub http_addr: SocketAddr,
    pub environment: String,
    pub database_url: Option<String>,
    pub max_body_bytes: usize,
    pub request_timeout_secs: u64,
    pub upstreams: Vec<Upstream>,
    pub auth_mode: AuthMode,
    pub auth_secret: Option<Vec<u8>>,
}

impl Config {
    pub fn from_env() -> Result<Self, GatewayError> {
        let http_addr = parse_socket_addr("APEX_HTTP_ADDR", "0.0.0.0:8085")?;
        let environment = env_str("APEX_ENVIRONMENT", "local");
        let database_url = std::env::var("APEX_DATABASE_URL").ok();
        let max_body_bytes = env_usize("APEX_GATEWAY_MAX_BODY_BYTES", 10 * 1024 * 1024)?;
        let request_timeout_secs = env_u64("APEX_GATEWAY_REQUEST_TIMEOUT_SECS", 5)?;

        let upstreams_raw = std::env::var("APEX_GATEWAY_UPSTREAMS")
            .unwrap_or_else(|_| default_upstreams_raw());

        let upstreams = parse_upstreams(&upstreams_raw)?;

        if upstreams.is_empty() {
            return Err(GatewayError::Config(
                "at least one upstream service must be configured".into(),
            ));
        }

        let auth_mode = parse_auth_mode(&env_str("APEX_GATEWAY_AUTH_MODE", "permissive"))?;

        let auth_secret = match std::env::var("APEX_AUTH_TOKEN_SECRET") {
            Ok(secret_b64) if !secret_b64.trim().is_empty() => {
                Some(decode_secret_b64(&secret_b64).map_err(|_| {
                    GatewayError::Config(
                        "APEX_AUTH_TOKEN_SECRET must be valid base64-encoded 32 bytes".into(),
                    )
                })?)
            }
            _ => None,
        };

        if auth_mode != AuthMode::Disabled && auth_secret.is_none() {
            return Err(GatewayError::Config(
                "APEX_AUTH_TOKEN_SECRET is required when gateway authentication is not disabled"
                    .into(),
            ));
        }

        validate_token("environment", &environment)?;

        Ok(Self {
            http_addr,
            environment,
            database_url,
            max_body_bytes,
            request_timeout_secs,
            upstreams,
            auth_mode,
            auth_secret,
        })
    }
}

fn parse_auth_mode(raw: &str) -> Result<AuthMode, GatewayError> {
    match raw.trim().to_ascii_lowercase().as_str() {
        "disabled" => Ok(AuthMode::Disabled),
        "permissive" => Ok(AuthMode::Permissive),
        "enforced" => Ok(AuthMode::Enforced),
        other => Err(GatewayError::Config(format!(
            "invalid APEX_GATEWAY_AUTH_MODE: {other}"
        ))),
    }
}

fn default_upstreams_raw() -> String {
    "service-framework-core|CONTROL|http://service-framework-core:8080;\
     database-infrastructure-core|CONTROL|http://database-infrastructure-core:8081"
        .to_string()
}

pub fn parse_upstreams(raw: &str) -> Result<Vec<Upstream>, GatewayError> {
    let mut upstreams = Vec::new();

    for entry in raw.split(';') {
        let entry = entry.trim();

        if entry.is_empty() {
            continue;
        }

        let parts: Vec<&str> = entry.split('|').map(|value| value.trim()).collect();

        if parts.len() != 3 {
            return Err(GatewayError::Config(format!(
                "invalid upstream entry: {entry}"
            )));
        }

        let service_name = parts[0].to_string();
        let plane = parts[1].to_string();
        let base_url_raw = parts[2].to_string();

        validate_service_name(&service_name)?;
        validate_plane(&plane)?;

        let base_url = Url::parse(&base_url_raw).map_err(|_| {
            GatewayError::Config(format!("invalid upstream URL: {base_url_raw}"))
        })?;

        if base_url.scheme() != "http" && base_url.scheme() != "https" {
            return Err(GatewayError::Config(format!(
                "upstream URL must use http or https: {base_url_raw}"
            )));
        }

        upstreams.push(Upstream {
            service_name,
            plane,
            base_url,
        });
    }

    Ok(upstreams)
}

fn validate_service_name(value: &str) -> Result<(), GatewayError> {
    if value.is_empty() {
        return Err(GatewayError::Config("service name must not be empty".into()));
    }

    if value.len() > 128 {
        return Err(GatewayError::Config("service name is too long".into()));
    }

    for character in value.chars() {
        let allowed = character.is_ascii_lowercase()
            || character.is_ascii_digit()
            || character == '-';

        if !allowed {
            return Err(GatewayError::Config(format!(
                "service name may only contain lowercase letters, digits, and hyphens: {value}"
            )));
        }
    }

    Ok(())
}

fn validate_plane(value: &str) -> Result<(), GatewayError> {
    if value.is_empty() {
        return Err(GatewayError::Config("plane must not be empty".into()));
    }

    if value.len() > 64 {
        return Err(GatewayError::Config("plane is too long".into()));
    }

    for character in value.chars() {
        let allowed = character.is_ascii_uppercase() || character == '_';

        if !allowed {
            return Err(GatewayError::Config(format!(
                "plane may only contain uppercase letters and underscores: {value}"
            )));
        }
    }

    Ok(())
}

fn env_str(key: &str, default: &str) -> String {
    std::env::var(key)
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| default.to_string())
}

fn env_usize(key: &str, default: usize) -> Result<usize, GatewayError> {
    let raw = env_str(key, &default.to_string());

    raw.parse::<usize>()
        .map_err(|_| GatewayError::Config(format!("{key} must be an unsigned integer")))
}

fn env_u64(key: &str, default: u64) -> Result<u64, GatewayError> {
    let raw = env_str(key, &default.to_string());

    raw.parse::<u64>()
        .map_err(|_| GatewayError::Config(format!("{key} must be an unsigned integer")))
}

fn parse_socket_addr(key: &str, default: &str) -> Result<SocketAddr, GatewayError> {
    let raw = env_str(key, default);

    raw.parse::<SocketAddr>()
        .map_err(|_| GatewayError::Config(format!("{key} must be a valid socket address")))
}

fn validate_token(field: &str, value: &str) -> Result<(), GatewayError> {
    if value.is_empty() {
        return Err(GatewayError::Config(format!("{field} must not be empty")));
    }

    if value.contains(char::is_whitespace) {
        return Err(GatewayError::Config(format!(
            "{field} must not contain whitespace"
        )));
    }

    Ok(())
}