use crate::db;
use crate::errors::Error;
use crate::metrics::Metrics;
use crate::pb::{ServiceDescriptor, ServiceEndpoint};
use crate::validation;
use axum::extract::{Path, Query, Request, State};
use axum::http::StatusCode;
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::json;
use sqlx::PgPool;
use std::sync::Arc;

pub struct AppState {
    pub pool: PgPool,
    pub metrics: Arc<Metrics>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct RegisterHttpRequest {
    #[serde(default)]
    pub service_id: Option<String>,
    pub service_name: String,
    pub version: String,
    pub environment: String,
    pub plane: String,
    pub fail_closed_policy: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub capabilities: Vec<String>,
    #[serde(default)]
    pub permissions: Vec<String>,
    #[serde(default)]
    pub endpoints: Vec<HttpEndpoint>,
    #[serde(default)]
    pub dependencies: Vec<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct HttpEndpoint {
    pub name: String,
    pub protocol: String,
    pub uri: String,
    pub port: i32,
}

#[derive(Debug, Deserialize)]
pub struct HeartbeatHttpRequest {
    pub service_id: String,
    pub state: String,
    #[serde(default)]
    pub detail: String,
}

#[derive(Debug, Deserialize)]
pub struct ListQuery {
    pub environment: Option<String>,
    pub plane: Option<String>,
    pub limit: Option<i64>,
    pub offset: Option<i64>,
}

pub enum ApiError {
    BadRequest(String),
    NotFound(String),
    ServiceUnavailable(String),
    Internal(String),
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let (status, message) = match &self {
            ApiError::BadRequest(message) => (StatusCode::BAD_REQUEST, message.clone()),
            ApiError::NotFound(message) => (StatusCode::NOT_FOUND, message.clone()),
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
            Error::Config(message) => ApiError::BadRequest(message),
            Error::InvalidArgument(message) => ApiError::BadRequest(message),
            Error::NotFound(message) => ApiError::NotFound(message),
            Error::Database(message) => ApiError::ServiceUnavailable(message),
            Error::Serialization(message) => ApiError::BadRequest(message),
            Error::Internal(message) => ApiError::Internal(message),
        }
    }
}

pub fn router(state: Arc<AppState>) -> Router {
    Router::new()
        .route("/healthz", get(healthz))
        .route("/readyz", get(readyz))
        .route("/metrics", get(metrics_handler))
        .route("/v1/services/register", post(register_service))
        .route("/v1/services/heartbeat", post(heartbeat))
        .route("/v1/services/:service_id", get(get_service))
        .route("/v1/services", get(list_services))
        .layer(axum::middleware::from_fn_with_state(
            state.clone(),
            http_metrics_middleware,
        ))
        .with_state(state)
}

async fn http_metrics_middleware(
    State(state): State<Arc<AppState>>,
    request: Request,
    next: Next,
) -> Response {
    let method = request.method().to_string();
    let path = request.uri().path().to_string();

    let timer = state
        .metrics
        .http_request_duration_seconds
        .with_label_values(&[&method, &path])
        .start_timer();

    let response = next.run(request).await;

    state
        .metrics
        .http_requests_total
        .with_label_values(&[&method, &path, response.status().as_str()])
        .inc();

    timer.observe_duration();

    response
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

async fn register_service(
    State(state): State<Arc<AppState>>,
    Json(payload): Json<RegisterHttpRequest>,
) -> Result<impl IntoResponse, ApiError> {
    let descriptor = descriptor_from_http(payload).map_err(ApiError::from)?;
    let descriptor = validation::normalize_descriptor(descriptor).map_err(ApiError::from)?;

    let timer = state
        .metrics
        .db_operation_duration_seconds
        .with_label_values(&["http_register_service"])
        .start_timer();

    let record = db::register_service(&state.pool, &descriptor)
        .await
        .map_err(ApiError::from)?;

    timer.observe_duration();

    state
        .metrics
        .registrations_total
        .with_label_values(&[&record.service_name, &record.plane])
        .inc();

    Ok((
        StatusCode::OK,
        Json(json!({
            "registration_id": record.service_id,
            "registered_at": record.created_at,
            "state": record.state
        })),
    ))
}

async fn heartbeat(
    State(state): State<Arc<AppState>>,
    Json(payload): Json<HeartbeatHttpRequest>,
) -> Result<impl IntoResponse, ApiError> {
    if payload.service_id.trim().is_empty() {
        return Err(ApiError::BadRequest("service_id is required".into()));
    }

    let state_i32 =
        validation::state_i32_from_str(&payload.state).map_err(ApiError::from)?;

    let observed_at = Utc::now();

    let timer = state
        .metrics
        .db_operation_duration_seconds
        .with_label_values(&["http_heartbeat"])
        .start_timer();

    let record = db::record_heartbeat(
        &state.pool,
        &payload.service_id,
        state_i32,
        &payload.detail,
        observed_at,
    )
    .await
    .map_err(ApiError::from)?;

    timer.observe_duration();

    state
        .metrics
        .heartbeats_total
        .with_label_values(&[&record.service_name, &record.plane, &record.state])
        .inc();

    Ok((
        StatusCode::OK,
        Json(json!({
            "acknowledged_at": observed_at,
            "state": record.state
        })),
    ))
}

async fn get_service(
    State(state): State<Arc<AppState>>,
    Path(service_id): Path<String>,
) -> Result<impl IntoResponse, ApiError> {
    let timer = state
        .metrics
        .db_operation_duration_seconds
        .with_label_values(&["http_get_service"])
        .start_timer();

    let maybe_record = db::get_service(&state.pool, &service_id)
        .await
        .map_err(ApiError::from)?;

    timer.observe_duration();

    let record = maybe_record
        .ok_or_else(|| ApiError::NotFound(format!("service {service_id} not found")))?;

    Ok((StatusCode::OK, Json(record)))
}

async fn list_services(
    State(state): State<Arc<AppState>>,
    Query(query): Query<ListQuery>,
) -> Result<impl IntoResponse, ApiError> {
    let environment = query
        .environment
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty());

    let plane = match query.plane {
        Some(raw) if !raw.trim().is_empty() => {
            let plane_i32 =
                validation::plane_i32_from_str(&raw).map_err(ApiError::from)?;
            let plane_db =
                validation::plane_to_db(plane_i32).map_err(ApiError::from)?;

            Some(plane_db.to_string())
        }
        _ => None,
    };

    let limit = query.limit.unwrap_or(100).clamp(1, 1000);
    let offset = query.offset.unwrap_or(0).max(0);

    let timer = state
        .metrics
        .db_operation_duration_seconds
        .with_label_values(&["http_list_services"])
        .start_timer();

    let (records, total) =
        db::list_services(&state.pool, environment, plane, limit, offset)
            .await
            .map_err(ApiError::from)?;

    timer.observe_duration();

    Ok((
        StatusCode::OK,
        Json(json!({
            "services": records,
            "total": total
        })),
    ))
}

fn descriptor_from_http(payload: RegisterHttpRequest) -> Result<ServiceDescriptor, Error> {
    let plane = validation::plane_i32_from_str(&payload.plane)?;
    let fail_closed_policy =
        validation::policy_i32_from_str(&payload.fail_closed_policy)?;

    let endpoints = payload
        .endpoints
        .into_iter()
        .map(|endpoint| ServiceEndpoint {
            name: endpoint.name,
            protocol: endpoint.protocol,
            uri: endpoint.uri,
            port: endpoint.port,
        })
        .collect();

    Ok(ServiceDescriptor {
        service_id: payload.service_id.unwrap_or_default(),
        service_name: payload.service_name,
        version: payload.version,
        environment: payload.environment,
        plane,
        fail_closed_policy,
        description: payload.description,
        capabilities: payload.capabilities,
        permissions: payload.permissions,
        endpoints,
        dependencies: payload.dependencies,
    })
}