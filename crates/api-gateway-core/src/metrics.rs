use crate::errors::GatewayError;
use prometheus::{
    Encoder, HistogramOpts, HistogramVec, IntCounterVec, Opts, Registry, TextEncoder,
};

#[derive(Clone)]
pub struct Metrics {
    pub registry: Registry,
    pub gateway_requests_total: IntCounterVec,
    pub gateway_request_duration_seconds: HistogramVec,
}

impl Metrics {
    pub fn new() -> Self {
        let registry = Registry::new();

        let gateway_requests_total = IntCounterVec::new(
            Opts::new("gateway_requests_total", "API gateway requests")
                .namespace("apexquant")
                .subsystem("api_gateway"),
            &["service", "method", "status"],
        )
        .expect("gateway_requests_total metric must be created");

        let gateway_request_duration_seconds = HistogramVec::new(
            HistogramOpts::new(
                "gateway_request_duration_seconds",
                "API gateway request duration in seconds",
            )
            .namespace("apexquant")
            .subsystem("api_gateway")
            .buckets(vec![
                0.000_1, 0.000_25, 0.000_5, 0.001, 0.002_5, 0.005, 0.01, 0.025, 0.05,
                0.1, 0.25, 0.5, 1.0, 2.5, 5.0,
            ]),
            &["service"],
        )
        .expect("gateway_request_duration_seconds metric must be created");

        registry
            .register(Box::new(gateway_requests_total.clone()))
            .expect("gateway_requests_total metric must register");

        registry
            .register(Box::new(gateway_request_duration_seconds.clone()))
            .expect("gateway_request_duration_seconds metric must register");

        Self {
            registry,
            gateway_requests_total,
            gateway_request_duration_seconds,
        }
    }

    pub fn encode(&self) -> Result<String, GatewayError> {
        let encoder = TextEncoder::new();
        let metric_families = self.registry.gather();
        let mut buffer = Vec::new();

        encoder
            .encode(&metric_families, &mut buffer)
            .map_err(|_| GatewayError::Internal)?;

        String::from_utf8(buffer).map_err(|_| GatewayError::Internal)
    }
}