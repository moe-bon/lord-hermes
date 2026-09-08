use thiserror::Error;

#[derive(Debug, Error)]
pub enum Error {
    #[error("configuration error: {0}")]
    Config(String),

    #[error("database error: {0}")]
    Database(#[from] sqlx::Error),

    #[error("serialization error: {0}")]
    Serialization(#[from] serde_json::Error),

    #[error("not found: {0}")]
    NotFound(String),

    #[error("invalid argument: {0}")]
    InvalidArgument(String),

    #[error("internal error: {0}")]
    Internal(String),
}

impl From<Error> for tonic::Status {
    fn from(value: Error) -> Self {
        match value {
            Error::Config(message) => tonic::Status::invalid_argument(message),
            Error::InvalidArgument(message) => tonic::Status::invalid_argument(message),
            Error::NotFound(message) => tonic::Status::not_found(message),
            Error::Database(message) => tonic::Status::unavailable(message),
            Error::Serialization(message) => tonic::Status::invalid_argument(message),
            Error::Internal(message) => tonic::Status::internal(message),
        }
    }
}