use crate::errors::Error;
use std::net::SocketAddr;

#[derive(Debug, Clone)]
pub struct Config {
    pub http_addr: SocketAddr,
    pub database_url: String,
    pub environment: String,
    pub instance_name: String,
    pub service_name: String,
    pub service_version: String,
    pub max_db_connections: u32,
}

impl Config {
    pub fn from_env() -> Result<Self, Error> {
        let http_addr = parse_socket_addr("APEX_HTTP_ADDR", "0.0.0.0:8081")?;
        let database_url = env_required("APEX_DATABASE_URL")?;
        let environment = env_str("APEX_ENVIRONMENT", "local");
        let instance_name = env_str("APEX_DB_INSTANCE_NAME", "apexquant-local");
        let service_name = env_str("APEX_SERVICE_NAME", "database-infrastructure-core");
        let service_version = env_str("APEX_SERVICE_VERSION", "0.6.0");
        let max_db_connections = env_u32("APEX_MAX_DB_CONNECTIONS", 10)?;

        validate_token("environment", &environment)?;
        validate_token("instance_name", &instance_name)?;
        validate_token("service_name", &service_name)?;
        validate_token("service_version", &service_version)?;

        Ok(Self {
            http_addr,
            database_url,
            environment,
            instance_name,
            service_name,
            service_version,
            max_db_connections,
        })
    }
}

fn env_required(key: &str) -> Result<String, Error> {
    std::env::var(key)
        .map(|value| value.trim().to_string())
        .map_err(|_| Error::Config(format!("{key} is required")))
        .and_then(|value| {
            if value.is_empty() {
                Err(Error::Config(format!("{key} must not be empty")))
            } else {
                Ok(value)
            }
        })
}

fn env_str(key: &str, default: &str) -> String {
    std::env::var(key)
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| default.to_string())
}

fn env_u32(key: &str, default: u32) -> Result<u32, Error> {
    let raw = env_str(key, &default.to_string());

    raw.parse::<u32>()
        .map_err(|_| Error::Config(format!("{key} must be an unsigned integer")))
}

fn parse_socket_addr(key: &str, default: &str) -> Result<SocketAddr, Error> {
    let raw = env_str(key, default);

    raw.parse::<SocketAddr>()
        .map_err(|_| Error::Config(format!("{key} must be a valid socket address")))
}

fn validate_token(field: &str, value: &str) -> Result<(), Error> {
    if value.is_empty() {
        return Err(Error::Config(format!("{field} must not be empty")));
    }

    if value.contains(char::is_whitespace) {
        return Err(Error::Config(format!("{field} must not contain whitespace")));
    }

    Ok(())
}