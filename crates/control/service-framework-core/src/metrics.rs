use crate::errors::Error;
use prometheus::{
    Encoder, HistogramOpts, HistogramVec, IntCounterVec, IntGaugeVec, Opts, Registry,
    TextEncoder,
};

#[derive(Clone)]
pub struct Metrics {
    pub registry: Registry,
    pub registrations_total: IntCounterVec,
    pub heartbeats_total: IntCounterVec,
    pub active_services: IntGaugeVec,
    pub http_requests_total: IntCounterVec,
    pub grpc_requests_total: IntCounterVec,
    pub db_operation_duration_seconds: HistogramVec,
    pub http_request_duration_seconds: HistogramVec,
}

impl Metrics {
    pub fn new() -> Self {
        let registry = Registry::new();

        let registrations_total = IntCounterVec::new(
            Opts::new("registrations_total", "Service registrations")
                .namespace("apexquant")
                .subsystem("service_framework"),
            &["service_name", "plane"],
        )
        .expect("registrations_total metric must be created");

        let heartbeats_total = IntCounterVec::new(
            Opts::new("heartbeats_total", "Service heartbeats")
                .namespace("apexquant")
                .subsystem("service_framework"),
            &["service_name", "plane", "state"],
        )
        .expect("heartbeats_total metric must be created");

        let active_services = IntGaugeVec::new(
            Opts::new("active_services", "Currently registered services")
                .namespace("apexquant")
                .subsystem("service_framework"),
            &["service_name", "plane", "state"],
        )
        .expect("active_services metric must be created");

        let http_requests_total = IntCounterVec::new(
            Opts::new("http_requests_total", "HTTP requests")
                .namespace("apexquant")
                .subsystem("service_framework"),
            &["method", "path", "status"],
        )
        .expect("http_requests_total metric must be created");

        let grpc_requests_total = IntCounterVec::new(
            Opts::new("grpc_requests_total", "gRPC requests")
                .namespace("apexquant")
                .subsystem("service_framework"),
            &["method", "status"],
        )
        .expect("grpc_requests_total metric must be created");

        let db_operation_duration_seconds = HistogramVec::new(
            HistogramOpts::new(
                "db_operation_duration_seconds",
                "Database operation duration in seconds",
            )
            .namespace("apexquant")
            .subsystem("service_framework")
            .buckets(vec![
                0.000_1, 0.000_25, 0.000_5, 0.001, 0.002_5, 0.005, 0.01, 0.025, 0.05,
                0.1, 0.25, 0.5, 1.0, 2.5, 5.0,
            ]),
            &["operation"],
        )
        .expect("db_operation_duration_seconds metric must be created");

        let http_request_duration_seconds = HistogramVec::new(
            HistogramOpts::new(
                "http_request_duration_seconds",
                "HTTP request duration in seconds",
            )
            .namespace("apexquant")
            .subsystem("service_framework")
            .buckets(vec![
                0.000_1, 0.000_25, 0.000_5, 0.001, 0.002_5, 0.005, 0.01, 0.025, 0.05,
                0.1, 0.25, 0.5, 1.0, 2.5, 5.0,
            ]),
            &["method", "path"],
        )
        .expect("http_request_duration_seconds metric must be created");

        registry
            .register(Box::new(registrations_total.clone()))
            .expect("registrations_total metric must register");
        registry
            .register(Box::new(heartbeats_total.clone()))
            .expect("heartbeats_total metric must register");
        registry
            .register(Box::new(active_services.clone()))
            .expect("active_services metric must register");
        registry
            .register(Box::new(http_requests_total.clone()))
            .expect("http_requests_total metric must register");
        registry
            .register(Box::new(grpc_requests_total.clone()))
            .expect("grpc_requests_total metric must register");
        registry
            .register(Box::new(db_operation_duration_seconds.clone()))
            .expect("db_operation_duration_seconds metric must register");
        registry
            .register(Box::new(http_request_duration_seconds.clone()))
            .expect("http_request_duration_seconds metric must register");

        Self {
            registry,
            registrations_total,
            heartbeats_total,
            active_services,
            http_requests_total,
            grpc_requests_total,
            db_operation_duration_seconds,
            http_request_duration_seconds,
        }
    }

    pub fn encode(&self) -> Result<String, Error> {
        let encoder = TextEncoder::new();
        let metric_families = self.registry.gather();
        let mut buffer = Vec::new();
        encoder
            .encode(&metric_families, &mut buffer)
            .map_err(|err| Error::Internal(format!("failed encoding metrics: {err}")))?;
        String::from_utf8(buffer).map_err(|err| Error::Internal(err.to_string()))
    }
}