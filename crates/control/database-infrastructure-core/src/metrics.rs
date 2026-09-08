use crate::errors::Error;
use prometheus::{
    Encoder, HistogramOpts, HistogramVec, IntCounterVec, Opts, Registry, TextEncoder,
};

#[derive(Clone)]
pub struct Metrics {
    pub registry: Registry,
    pub database_checks_total: IntCounterVec,
    pub database_check_duration_seconds: HistogramVec,
    pub http_requests_total: IntCounterVec,
}

impl Metrics {
    pub fn new() -> Self {
        let registry = Registry::new();

        let database_checks_total = IntCounterVec::new(
            Opts::new(
                "database_checks_total",
                "Database infrastructure verification checks",
            )
            .namespace("apexquant")
            .subsystem("database_infrastructure"),
            &["result"],
        )
        .expect("database_checks_total metric must be created");

        let database_check_duration_seconds = HistogramVec::new(
            HistogramOpts::new(
                "database_check_duration_seconds",
                "Database verification duration in seconds",
            )
            .namespace("apexquant")
            .subsystem("database_infrastructure")
            .buckets(vec![
                0.000_1, 0.000_25, 0.000_5, 0.001, 0.002_5, 0.005, 0.01, 0.025, 0.05,
                0.1, 0.25, 0.5, 1.0, 2.5, 5.0,
            ]),
            &["operation"],
        )
        .expect("database_check_duration_seconds metric must be created");

        let http_requests_total = IntCounterVec::new(
            Opts::new("http_requests_total", "HTTP requests")
                .namespace("apexquant")
                .subsystem("database_infrastructure"),
            &["method", "path", "status"],
        )
        .expect("http_requests_total metric must be created");

        registry
            .register(Box::new(database_checks_total.clone()))
            .expect("database_checks_total metric must register");

        registry
            .register(Box::new(database_check_duration_seconds.clone()))
            .expect("database_check_duration_seconds metric must register");

        registry
            .register(Box::new(http_requests_total.clone()))
            .expect("http_requests_total metric must register");

        Self {
            registry,
            database_checks_total,
            database_check_duration_seconds,
            http_requests_total,
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