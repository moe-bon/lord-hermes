use axum::{response::IntoResponse, routing::get, Json, Router};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::PgPool;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::RwLock;
use uuid::Uuid;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum HealthStatus {
    Healthy,
    Degraded,
    Unhealthy,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DependencyStatus {
    pub status: HealthStatus,
    pub latency_ms: Option<f64>,
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HealthResponse {
    pub status: HealthStatus,
    pub service: String,
    pub version: String,
    pub plane: String,
    pub environment: String,
    pub instance_id: String,
    pub timestamp: DateTime<Utc>,
    pub dependencies: std::collections::HashMap<String, DependencyStatus>,
}

#[async_trait::async_trait]
pub trait DependencyCheck: Send + Sync {
    fn name(&self) -> &str;
    fn check_type(&self) -> &str;
    async fn check(&self) -> DependencyStatus;
}

pub struct HealthChecker {
    pub service: String,
    pub version: String,
    pub plane: String,
    pub environment: String,
    pub instance_id: String,
    checks: RwLock<Vec<Arc<dyn DependencyCheck>>>,
}

impl HealthChecker {
    pub fn new(service: &str, version: &str, plane: &str, environment: &str) -> Self {
        Self {
            service: service.to_string(),
            version: version.to_string(),
            plane: plane.to_string(),
            environment: environment.to_string(),
            instance_id: format!("{}-{}", service, Uuid::new_v4()),
            checks: RwLock::new(Vec::new()),
        }
    }

    pub async fn add_check(&self, check: Arc<dyn DependencyCheck>) {
        self.checks.write().await.push(check);
    }

    pub async fn check_ready(&self) -> bool {
        let checks = self.checks.read().await;
        if checks.is_empty() {
            return true;
        }

        let mut handles = Vec::new();
        for check in checks.iter() {
            let c = check.clone();
            handles.push(tokio::spawn(async move {
                tokio::time::timeout(Duration::from_secs(2), c.check()).await
            }));
        }

        for handle in handles {
            match handle.await {
                Ok(Ok(status)) => {
                    if status.status != HealthStatus::Healthy {
                        return false;
                    }
                }
                _ => return false,
            }
        }
        true
    }

    pub async fn check_health(&self) -> HealthResponse {
        let checks = self.checks.read().await;
        let mut dependencies = std::collections::HashMap::new();
        let mut overall = HealthStatus::Healthy;

        for check in checks.iter() {
            let start = Instant::now();
            let status = tokio::time::timeout(Duration::from_secs(2), check.check())
                .await
                .unwrap_or_else(|_| DependencyStatus {
                    status: HealthStatus::Unhealthy,
                    latency_ms: None,
                    error: Some("timeout".to_string()),
                });

            let key = format!("{}:{}", check.check_type(), check.name());
            dependencies.insert(key, status);
        }

        if dependencies.values().any(|s| s.status == HealthStatus::Unhealthy) {
            overall = HealthStatus::Unhealthy;
        }

        HealthResponse {
            status: overall,
            service: self.service.clone(),
            version: self.version.clone(),
            plane: self.plane.clone(),
            environment: self.environment.clone(),
            instance_id: self.instance_id.clone(),
            timestamp: Utc::now(),
            dependencies,
        }
    }
}

pub fn health_router(checker: Arc<HealthChecker>) -> Router {
    Router::new()
        .route("/livez", get(|| async { Json(serde_json::json!({"status": "alive"})) }))
        .route(
            "/readyz",
            get({
                let checker = checker.clone();
                move || async move {
                    if checker.check_ready().await {
                        Json(serde_json::json!({"status": "ready"})).into_response()
                    } else {
                        (
                            axum::http::StatusCode::SERVICE_UNAVAILABLE,
                            Json(serde_json::json!({"status": "not_ready"})),
                        )
                            .into_response()
                    }
                }
            }),
        )
        .route(
            "/healthz",
            get({
                let checker = checker.clone();
                move || async move {
                    let health = checker.check_health().await;
                    let status = if health.status == HealthStatus::Unhealthy {
                        axum::http::StatusCode::SERVICE_UNAVAILABLE
                    } else {
                        axum::http::StatusCode::OK
                    };
                    (status, Json(health)).into_response()
                }
            }),
        )
}