use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::json;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum GatewayError {
    #[error("configuration error: {0}")]
    Config(String),

    #[error("database error: {0}")]
    Database(String),

    #[error("upstream service not found")]
    UpstreamNotFound,

    #[error("method not allowed")]
    MethodNotAllowed,

    #[error("request body too large")]
    BodyTooLarge,

    #[error("bad gateway")]
    BadGateway,

    #[error("gateway timeout")]
    GatewayTimeout,

    #[error("internal gateway error")]
    Internal,
}

impl GatewayError {
    pub fn status(&self) -> StatusCode {
        match self {
            GatewayError::Config(_) => StatusCode::INTERNAL_SERVER_ERROR,
            GatewayError::Database(_) => StatusCode::SERVICE_UNAVAILABLE,
            GatewayError::UpstreamNotFound => StatusCode::NOT_FOUND,
            GatewayError::MethodNotAllowed => StatusCode::METHOD_NOT_ALLOWED,
            GatewayError::BodyTooLarge => StatusCode::PAYLOAD_TOO_LARGE,
            GatewayError::BadGateway => StatusCode::BAD_GATEWAY,
            GatewayError::GatewayTimeout => StatusCode::GATEWAY_TIMEOUT,
            GatewayError::Internal => StatusCode::INTERNAL_SERVER_ERROR,
        }
    }

    pub fn code(&self) -> &'static str {
        match self {
            GatewayError::Config(_) => "CONFIGURATION_ERROR",
            GatewayError::Database(_) => "DATABASE_ERROR",
            GatewayError::UpstreamNotFound => "UPSTREAM_NOT_FOUND",
            GatewayError::MethodNotAllowed => "METHOD_NOT_ALLOWED",
            GatewayError::BodyTooLarge => "BODY_TOO_LARGE",
            GatewayError::BadGateway => "BAD_GATEWAY",
            GatewayError::GatewayTimeout => "GATEWAY_TIMEOUT",
            GatewayError::Internal => "INTERNAL_ERROR",
        }
    }
}

impl From<sqlx::Error> for GatewayError {
    fn from(value: sqlx::Error) -> Self {
        GatewayError::Database(value.to_string())
    }
}

impl IntoResponse for GatewayError {
    fn into_response(self) -> Response {
        let status = self.status();

        let body = Json(json!({
            "error": {
                "code": self.code(),
                "message": self.to_string()
            }
        }));

        (status, body).into_response()
    }
}
