use thiserror::Error;

#[derive(Debug, Error)]
pub enum RedisError {
    #[error("configuration error: {0}")]
    Config(String),

    #[error("redis connection error: {0}")]
    Connection(#[from] redis::RedisError),

    #[error("lock acquisition failed: {0}")]
    LockFailed(String),

    #[error("lock release failed: {0}")]
    ReleaseFailed(String),

    #[error("internal error: {0}")]
    Internal(String),
}