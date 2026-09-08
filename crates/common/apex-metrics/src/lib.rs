use axum::extract::MatchedPath;
use axum::middleware::{self, Next};
use axum::response::IntoResponse;
use axum::routing::get;
use axum::Router;
use prometheus::{
    Encoder, HistogramOpts, HistogramVec, IntCounterVec, Opts, Registry, TextEncoder,
};
use std::sync::Arc;
use std::time::Instant;
use thiserror::Error;

const FORBIDDEN_HIGH_CARDINALITY_LABELS: &[&str] = &[
    "user_id",
    "request_id",
    "trace_id",
    "correlation_id",
    "session_id",
    "ip_address",
    "email",
    "username",
];

const STANDARD_LABELS: &[&str] = &["service", "environment", "plane", "version"];

#[derive(Debug, Error)]
pub enum MetricGovernanceError {
    #[error("metric name '{0}' violates naming convention")]
    InvalidName(String),

    #[error("high-cardinality label '{0}' is forbidden")]
    ForbiddenLabel(String),

    #[error("prometheus error: {0}")]
    Prometheus(#[from] prometheus::Error),
}

#[derive(Clone)]
pub struct ApexMetricRegistry {
    pub registry: Registry,
    pub standard_labels: Vec<(String, String)>,
}

impl ApexMetricRegistry {
    pub fn new(
        service_name: &str,
        environment: &str,
        plane: &str,
        version: &str,
    ) -> Self {
        let registry = Registry::new();

        let standard_labels = vec![
            ("service".to_string(), service_name.to_string()),
            ("environment".to_string(), environment.to_string()),
            ("plane".to_string(), plane.to_string()),
            ("version".to_string(), version.to_string()),
        ];

        Self {
            registry,
            standard_labels,
        }
    }

    fn validate_name(&self, name: &str) -> Result<(), MetricGovernanceError> {
        let parts: Vec<&str> = name.split('_').collect();

        if parts.len() < 3 || parts[0] != "apexquant" {
            return Err(MetricGovernanceError::InvalidName(name.to_string()));
        }

        Ok(())
    }

    fn validate_labels(&self, labels: &[&str]) -> Result<Vec<String>, MetricGovernanceError> {
        for label in labels {
            if FORBIDDEN_HIGH_CARDINALITY_LABELS.contains(label) {
                return Err(MetricGovernanceError::ForbiddenLabel(label.to_string()));
            }
        }

        let mut combined: Vec<String> = STANDARD_LABELS.iter().map(|s| s.to_string()).collect();

        for label in labels {
            if !combined.contains(&label.to_string()) {
                combined.push(label.to_string());
            }
        }

        Ok(combined)
    }

    pub fn counter(
        &self,
        name: &str,
        description: &str,
        labels: &[&str],
    ) -> Result<IntCounterVec, MetricGovernanceError> {
        self.validate_name(name)?;
        let all_labels = self.validate_labels(labels)?;
        let label_refs: Vec<&str> = all_labels.iter().map(|s| s.as_str()).collect();

        let opts = Opts::new(name, description);
        let counter = IntCounterVec::new(opts, &label_refs)?;

        self.registry.register(Box::new(counter.clone()))?;

        Ok(counter)
    }

    pub fn histogram(
        &self,
        name: &str,
        description: &str,
        labels: &[&str],
        buckets: Option<Vec<f64>>,
    ) -> Result<HistogramVec, MetricGovernanceError> {
        self.validate_name(name)?;
        let all_labels = self.validate_labels(labels)?;
        let label_refs: Vec<&str> = all_labels.iter().map(|s| s.as_str()).collect();

        let mut opts = HistogramOpts::new(name, description);

        if let Some(b) = buckets {
            opts = opts.buckets(b);
        }

        let histogram = HistogramVec::new(opts, &label_refs)?;

        self.registry.register(Box::new(histogram.clone()))?;

        Ok(histogram)
    }

    pub fn encode(&self) -> Result<String, MetricGovernanceError> {
        let encoder = TextEncoder::new();
        let metric_families = self.registry.gather();
        let mut buffer = Vec::new();

        encoder.encode(&metric_families, &mut buffer)?;

        String::from_utf8(buffer).map_err(|e| MetricGovernanceError::Prometheus(prometheus::Error::Msg(e.to_string())))
    }

    pub fn standard_label_values(&self) -> Vec<String> {
        self.standard_labels.iter().map(|(_, v)| v.clone()).collect()
    }
}

pub struct HttpMetrics {
    pub requests_total: IntCounterVec,
    pub request_duration_seconds: HistogramVec,
}

impl HttpMetrics {
    pub fn new(registry: &ApexMetricRegistry) -> Result<Self, MetricGovernanceError> {
        let requests_total = registry.counter(
            "apexquant_http_requests_total",
            "Total HTTP requests",
            &["method", "path", "status"],
        )?;

        let request_duration_seconds = registry.histogram(
            "apexquant_http_request_duration_seconds",
            "HTTP request duration in seconds",
            &["method", "path"],
            Some(vec![0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]),
        )?;

        Ok(Self {
            requests_total,
            request_duration_seconds,
        })
    }
}

pub fn metrics_router(registry: Arc<ApexMetricRegistry>) -> Router {
    Router::new().route("/metrics", get(move || async move {
        match registry.encode() {
            Ok(body) => (
                [(axum::http::header::CONTENT_TYPE, "text/plain; version=0.0.4")],
                body,
            )
                .into_response(),
            Err(_) => axum::http::StatusCode::INTERNAL_SERVER_ERROR.into_response(),
        }
    }))
}

pub async fn http_metrics_middleware(
    axum::extract::State(metrics): axum::extract::State<Arc<HttpMetrics>>,
    axum::extract::State(registry): axum::extract::State<Arc<ApexMetricRegistry>>,
    request: axum::extract::Request,
    next: Next,
) -> axum::response::Response {
    let method = request.method().to_string();
    let path = request
        .extensions()
        .get::<MatchedPath>()
        .map(|p| p.as_str().to_string())
        .unwrap_or_else(|| request.uri().path().to_string());

    let standard_values = registry.standard_label_values();

    let started_at = Instant::now();

    let response = next.run(request).await;

    let duration = started_at.elapsed().as_secs_f64();
    let status = response.status().as_u16().to_string();

    let mut duration_labels = standard_values.clone();
    duration_labels.push(method.clone());
    duration_labels.push(path.clone());

    let mut total_labels = duration_labels.clone();
    total_labels.push(status);

    if let Ok(histogram) = metrics.request_duration_seconds.get_metric_with_label_values(
        &duration_labels.iter().map(|s| s.as_str()).collect::<Vec<_>>(),
    ) {
        histogram.observe(duration);
    }

    if let Ok(counter) = metrics.requests_total.get_metric_with_label_values(
        &total_labels.iter().map(|s| s.as_str()).collect::<Vec<_>>(),
    ) {
        counter.inc();
    }

    response
}