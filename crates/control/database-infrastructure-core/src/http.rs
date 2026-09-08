use crate::db;
use crate::errors::Error;
use crate::metrics::Metrics;
use crate::config::Config;
use axum::extract::State;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::{Json, Router};
use serde_json::json;
use sqlx::PgPool;
use std::sync::Arc;

pub struct AppState {
    pub pool: PgPool,
    pub metrics: Arc<Metrics>,
    pub config: Config,
}

pub enum ApiError {
    ServiceUnavailable(String),
    Internal(String),
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let (status, message) = match &self {
            ApiError::ServiceUnavailable(message) => {
                (StatusCode::SERVICE_UNAVAILABLE, message.clone())
            }
            ApiError::Internal(message) => {
                (StatusCode::INTERNAL_SERVER_ERROR, message.clone())
            }
        };

        (status, Json(json!({ "error": message }))).into_response()
    }
}

impl From<Error> for ApiError {
    fn from(value: Error) -> Self {
        match value {
            Error::Database(message) => ApiError::ServiceUnavailable(message.to_string()),
            Error::Config(message) => ApiError::Internal(message),
            Error::Serialization(message) => ApiError::Internal(message.to_string()),
            Error::Internal(message) => ApiError::Internal(message),
        }
    }
}

pub fn router(state: Arc<AppState>) -> Router {
    Router::new()
        .route("/healthz", get(healthz))
        .route("/readyz", get(readyz))
        .route("/metrics", get(metrics_handler))
        .route("/v1/database/report", get(database_report))
        .with_state(state)
}

async fn healthz() -> impl IntoResponse {
    Json(json!({ "status": "ok" }))
}

async fn readyz(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    match state.pool.ping().await {
        Ok(_) => (StatusCode::OK, Json(json!({ "ready": true }))),
        Err(_) => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({ "ready": false })),
        ),
    }
}

async fn metrics_handler(
    State(state): State<Arc<AppState>>,
) -> Result<impl IntoResponse, ApiError> {
    let body = state.metrics.encode().map_err(ApiError::from)?;

    Ok((
        [(
            axum::http::header::CONTENT_TYPE,
            "text/plain; version=0.0.4",
        )],
        body,
    ))
}

async fn database_report(
    State(state): State<Arc<AppState>>,
) -> Result<impl IntoResponse, ApiError> {
    let timer = state
        .metrics
        .database_check_duration_seconds
        .with_label_values(&["http_database_report"])
        .start_timer();

    let report = db::run_checks(&state.pool, &state.config.environment, &state.config.instance_name)
        .await
        .map_err(ApiError::from)?;

    db::persist_report(&state.pool, &report)
        .await
        .map_err(ApiError::from)?;

    timer.observe_duration();

    if report.ok {
        state
            .metrics
            .database_checks_total
            .with_label_values(&["pass"])
            .inc();
    } else {
        state
            .metrics
            .database_checks_total
            .with_label_values(&["fail"])
            .inc();
    }

    Ok((StatusCode::OK, Json(report)))
}