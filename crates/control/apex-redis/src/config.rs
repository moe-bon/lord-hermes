use crate::errors::RedisError;

#[derive(Debug, Clone)]
pub struct RedisConfig {
    pub url: String,
    pub max_retries: u32,
}

impl RedisConfig {
    pub fn from_env() -> Result<Self, RedisError> {
        let url = std::env::var("APEX_REDIS_URL")
            .map(|value| value.trim().to_string())
            .map_err(|_| RedisError::Config("APEX_REDIS_URL is required".into()))?;

        if url.is_empty() {
            return Err(RedisError::Config("APEX_REDIS_URL must not be empty".into()));
        }

        let max_retries = std::env::var("APEX_REDIS_MAX_RETRIES")
            .ok()
            .and_then(|value| value.parse::<u32>().ok())
            .unwrap_or(3);

        Ok(Self { url, max_retries })
    }
}