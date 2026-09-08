use crate::config::{AuthMode, Config};
use crate::errors::GatewayError;
use crate::metrics::Metrics;
use crate::persistence;
use crate::registry::RouteRegistry;
use apex_auth::{verify_token, AuthContext};
use axum::body::{to_bytes, Body};
use axum::extract::{Extension, Path, State};
use axum::http::{header, HeaderValue, Method, StatusCode};
use axum::middleware::{self, Next};
use axum::response::{IntoResponse, Response};
use axum::routing::{any, get};
use axum::{Json, Router};
use serde_json::{json, Value};
use sqlx::PgPool;
use std::sync::Arc;
use std::time::Duration;
use uuid::Uuid;

pub struct AppState {
    pub config: Config,
    pub registry: RouteRegistry,
    pub metrics: Arc<Metrics>,
    pub client: reqwest::Client,
    pub pool: Option<PgPool>,
}

#[derive(Clone)]
pub struct RequestId(pub String);

pub fn router(state: Arc<AppState>) -> Router {
    Router::new()
        .route("/healthz", get(healthz))
        .route("/readyz", get(readyz))
        .route("/metrics", get(metrics_handler))
        .route("/v1/gateway/routes", get(routes))
        .route("/v1/gateway/verify", get(verify))
        .route("/api/:service", any(proxy_root))
        .route("/api/:service/*path", any(proxy))
        .layer(middleware::from_fn(request_context))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            authenticate_request,
        ))
        .with_state(state)
}

async fn request_context(mut request: axum::extract::Request, next: Next) -> Response {
    let request_id = request
        .headers()
        .get("x-request-id")
        .and_then(|value| value.to_str().ok())
        .map(|value| value.to_string())
        .unwrap_or_else(|| Uuid::new_v4().to_string());

    request.extensions_mut().insert(RequestId(request_id.clone()));

    let mut response = next.run(request).await;

    if let Ok(header_value) = HeaderValue::from_str(&request_id) {
        response.headers_mut().insert("x-request-id", header_value);
    }

    response.headers_mut().insert(
        "x-apex-gateway",
        HeaderValue::from_static("apexquant-api-gateway"),
    );

    response
}

async fn authenticate_request(
    State(state): State<Arc<AppState>>,
    mut request: axum::extract::Request,
    next: Next,
) -> Response {
    let path = request.uri().path().to_string();
    let protected = path.starts_with("/api/");

    if !protected || state.config.auth_mode == AuthMode::Disabled {
        return next.run(request).await;
    }

    let auth_header = request
        .headers()
        .get(header::AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        .map(|value| value.to_string());

    let token = match auth_header {
        Some(value) if value.starts_with("Bearer ") => value.trim_start_matches("Bearer ").to_string(),
        Some(_) => {
            state
                .metrics
                .gateway_auth_failures_total
                .with_label_values(&["invalid_authorization_header"])
                .inc();

            return unauthorized("invalid authorization header format");
        }
        None => {
            if state.config.auth_mode == AuthMode::Enforced {
                state
                    .metrics
                    .gateway_auth_failures_total
                    .with_label_values(&["missing_token"])
                    .inc();

                return unauthorized("authentication token is required");
            }

            return next.run(request).await;
        }
    };

    let secret = match &state.config.auth_secret {
        Some(secret) => secret,
        None => {
            state
                .metrics
                .gateway_auth_failures_total
                .with_label_values(&["missing_gateway_secret"])
                .inc();

            return unauthorized("gateway authentication secret is not configured");
        }
    };

    let now = apex_auth::now_unix();

    match verify_token(secret, &token, now) {
        Ok(context) => {
            request.extensions_mut().insert(context);
            next.run(request).await
        }
        Err(err) => {
            state
                .metrics
                .gateway_auth_failures_total
                .with_label_values(&["invalid_token"])
                .inc();

            unauthorized(&format!("authentication failed: {err}"))
        }
    }
}

fn unauthorized(message: &str) -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(json!({
            "error": {
                "code": "UNAUTHORIZED",
                "message": message
            }
        })),
    )
        .into_response()
}

async fn healthz() -> impl IntoResponse {
    Json(json!({ "status": "ok" }))
}

async fn readyz(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    if state.registry.services().next().is_none() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({ "ready": false })),
        );
    }

    (StatusCode::OK, Json(json!({ "ready": true })))
}

async fn metrics_handler(
    State(state): State<Arc<AppState>>,
) -> Result<impl IntoResponse, GatewayError> {
    let body = state.metrics.encode()?;

    Ok((
        [(
            header::CONTENT_TYPE,
            "text/plain; version=0.0.4",
        )],
        body,
    ))
}

async fn routes(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    Json(json!({
        "routes": state.registry.summary()
    }))
}

async fn verify(State(state): State<Arc<AppState>>) -> Result<Response, GatewayError> {
    let mut checks = Vec::new();
    let mut ok = true;

    for upstream in state.registry.services() {
        let health_url = upstream
            .base_url
            .join("healthz")
            .map_err(|_| GatewayError::Internal)?;

        let healthy = match state.client.get(health_url.clone()).send().await {
            Ok(response) => response.status().is_success(),
            Err(_) => false,
        };

        if !healthy {
            ok = false;
        }

        checks.push(json!({
            "service_name": upstream.service_name,
            "plane": upstream.plane,
            "health_url": health_url.to_string(),
            "healthy": healthy
        }));
    }

    let report = json!({
        "environment": state.config.environment,
        "ok": ok,
        "checks": checks
    });

    if let Some(pool) = &state.pool {
        persistence::persist_verification(pool, &state.config.environment, ok, report.clone())
            .await?;
    }

    let status = if ok {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    };

    Ok((status, Json(report)).into_response())
}

async fn proxy_root(
    State(state): State<Arc<AppState>>,
    Extension(request_id): Extension<RequestId>,
    Path(service): Path<String>,
    request: axum::extract::Request,
) -> Result<Response, GatewayError> {
    proxy_service(state, request_id, service, request).await
}

async fn proxy(
    State(state): State<Arc<AppState>>,
    Extension(request_id): Extension<RequestId>,
    Path((service, _path)): Path<(String, String)>,
    request: axum::extract::Request,
) -> Result<Response, GatewayError> {
    proxy_service(state, request_id, service, request).await
}

async fn proxy_service(
    state: Arc<AppState>,
    request_id: RequestId,
    service: String,
    request: axum::extract::Request,
) -> Result<Response, GatewayError> {
    let upstream = state
        .registry
        .get(&service)
        .ok_or(GatewayError::UpstreamNotFound)?;

    if !matches!(
        request.method(),
        &Method::GET | &Method::POST | &Method::HEAD
    ) {
        return Err(GatewayError::MethodNotAllowed);
    }

    let timer = state
        .metrics
        .gateway_request_duration_seconds
        .with_label_values(&[&service])
        .start_timer();

    let mut url = upstream.base_url.clone();

    let raw_path = request.uri().path();
    let prefix = format!("/api/{service}");
    let remaining_path = raw_path.strip_prefix(&prefix).unwrap_or("");

    {
        let mut segments = url
            .path_segments_mut()
            .map_err(|_| GatewayError::Internal)?;

        for segment in remaining_path.trim_start_matches('/').split('/') {
            if !segment.is_empty() {
                segments.push(segment);
            }
        }
    }

    url.set_query(request.uri().query());

    let body = to_bytes(request.into_body(), state.config.max_body_bytes)
        .await
        .map_err(|_| GatewayError::BodyTooLarge)?;

    let method = reqwest::Method::from_bytes(request.method().as_str().as_bytes())
        .map_err(|_| GatewayError::MethodNotAllowed)?;

    let mut headers = reqwest::header::HeaderMap::new();

    for (name, value) in request.headers() {
        let name_str = name.as_str();

        let should_forward = name == header::CONTENT_TYPE
            || name == header::ACCEPT
            || name_str.starts_with("x-apex-");

        if !should_forward {
            continue;
        }

        if let (Ok(reqwest_name), Ok(reqwest_value)) = (
            reqwest::header::HeaderName::from_bytes(name_str.as_bytes()),
            reqwest::header::HeaderValue::from_bytes(value.as_bytes()),
        ) {
            headers.insert(reqwest_name, reqwest_value);
        }
    }

    headers.insert(
        "x-request-id",
        reqwest::header::HeaderValue::from_str(&request_id.0)
            .map_err(|_| GatewayError::Internal)?,
    );

    if let Some(context) = request.extensions().get::<AuthContext>() {
        headers.insert(
            "x-apex-auth-subject",
            reqwest::header::HeaderValue::from_str(&context.subject)
                .map_err(|_| GatewayError::Internal)?,
        );

        headers.insert(
            "x-apex-auth-principal-type",
            reqwest::header::HeaderValue::from_str(&context.principal_type)
                .map_err(|_| GatewayError::Internal)?,
        );
    }

    let upstream_response = state
        .client
        .request(method, url)
        .headers(headers)
        .body(body.to_vec())
        .send()
        .await
        .map_err(|err| {
            if err.is_timeout() {
                GatewayError::GatewayTimeout
            } else {
                GatewayError::BadGateway
            }
        })?;

    let status = StatusCode::from_u16(upstream_response.status().as_u16())
        .unwrap_or(StatusCode::BAD_GATEWAY);

    let response_body = upstream_response
        .bytes()
        .await
        .map_err(|_| GatewayError::BadGateway)?;

    timer.observe_duration();

    state
        .metrics
        .gateway_requests_total
        .with_label_values(&[&service, request.method().as_str(), status.as_str()])
        .inc();

    let mut response = Response::new(Body::from(response_body));
    *response.status() = status;

    response.headers_mut().insert(
        "x-request-id",
        HeaderValue::from_str(&request_id.0).map_err(|_| GatewayError::Internal)?,
    );

    response.headers_mut().insert(
        "x-apex-upstream-service",
        HeaderValue::from_str(&service).map_err(|_| GatewayError::Internal)?,
    );

    Ok(response)
}