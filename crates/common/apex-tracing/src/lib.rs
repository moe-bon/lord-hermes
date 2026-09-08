use rand::Rng;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use thiserror::Error;

const ZERO_TRACE_ID: &str = "00000000000000000000000000000000";
const ZERO_SPAN_ID: &str = "0000000000000000";

#[derive(Debug, Error)]
pub enum TracingError {
    #[error("invalid traceparent header")]
    InvalidTraceparent,

    #[error("unsupported traceparent version")]
    UnsupportedVersion,

    #[error("invalid trace identifier")]
    InvalidTraceId,

    #[error("invalid span identifier")]
    InvalidSpanId,

    #[error("invalid trace flags")]
    InvalidTraceFlags,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TraceContext {
    pub trace_id: String,
    pub span_id: String,
    pub trace_flags: u8,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tracestate: Option<String>,
}

impl TraceContext {
    pub fn sampled(&self) -> bool {
        self.trace_flags & 0x01 == 0x01
    }
}

fn is_lowercase_hex(value: &str) -> bool {
    !value.is_empty() && value.chars().all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
}

pub fn generate_trace_id() -> String {
    let mut rng = rand::thread_rng();

    loop {
        let bytes: [u8; 16] = rng.gen();
        let value = hex_encode(&bytes);

        if value != ZERO_TRACE_ID {
            return value;
        }
    }
}

pub fn generate_span_id() -> String {
    let mut rng = rand::thread_rng();

    loop {
        let bytes: [u8; 8] = rng.gen();
        let value = hex_encode(&bytes);

        if value != ZERO_SPAN_ID {
            return value;
        }
    }
}

fn hex_encode(bytes: &[u8]) -> String {
    let mut value = String::with_capacity(bytes.len() * 2);

    for byte in bytes {
        value.push_str(&format!("{byte:02x}"));
    }

    value
}

pub fn parse_traceparent(header: &str) -> Result<TraceContext, TracingError> {
    let parts: Vec<&str> = header.trim().split('-').collect();

    if parts.len() != 4 {
        return Err(TracingError::InvalidTraceparent);
    }

    let version = parts[0];
    let trace_id = parts[1];
    let span_id = parts[2];
    let flags = parts[3];

    if version != "00" {
        return Err(TracingError::UnsupportedVersion);
    }

    if trace_id.len() != 32 || !is_lowercase_hex(trace_id) || trace_id == ZERO_TRACE_ID {
        return Err(TracingError::InvalidTraceId);
    }

    if span_id.len() != 16 || !is_lowercase_hex(span_id) || span_id == ZERO_SPAN_ID {
        return Err(TracingError::InvalidSpanId);
    }

    if flags.len() != 2 || !is_lowercase_hex(flags) {
        return Err(TracingError::InvalidTraceFlags);
    }

    let trace_flags = u8::from_str_radix(flags, 16)
        .map_err(|_| TracingError::InvalidTraceFlags)?;

    Ok(TraceContext {
        trace_id: trace_id.to_string(),
        span_id: span_id.to_string(),
        trace_flags,
        tracestate: None,
    })
}

pub fn format_traceparent(context: &TraceContext) -> String {
    format!(
        "00-{}-{}-{:02x}",
        context.trace_id, context.span_id, context.trace_flags
    )
}

pub fn new_root_context(sampled: bool) -> TraceContext {
    TraceContext {
        trace_id: generate_trace_id(),
        span_id: generate_span_id(),
        trace_flags: if sampled { 1 } else { 0 },
        tracestate: None,
    }
}

pub struct DeterministicSampler {
    ratio: f64,
}

impl DeterministicSampler {
    pub fn new(ratio: f64) -> Self {
        Self {
            ratio: ratio.clamp(0.0, 1.0),
        }
    }

    pub fn should_sample(&self, trace_id: &str) -> bool {
        if self.ratio <= 0.0 {
            return false;
        }

        if self.ratio >= 1.0 {
            return true;
        }

        if trace_id.len() != 32 {
            return false;
        }

        let value = match u32::from_str_radix(&trace_id[..8], 16) {
            Ok(value) => value,
            Err(_) => return false,
        };

        let threshold = (self.ratio * u32::MAX as f64) as u32;

        value <= threshold
    }
}

const SECRET_KEY_MARKERS: &[&str] = &[
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "credential",
    "access_key",
    "authorization",
];

pub fn is_secret_key(key: &str) -> bool {
    let normalized = key.to_ascii_lowercase();

    SECRET_KEY_MARKERS
        .iter()
        .any(|marker| normalized.contains(marker))
}

pub fn redact_attributes(attributes: &BTreeMap<String, String>) -> BTreeMap<String, String> {
    let mut redacted = BTreeMap::new();

    for (key, value) in attributes {
        if is_secret_key(key) {
            redacted.insert(key.clone(), "[REDACTED]".to_string());
        } else {
            redacted.insert(key.clone(), value.clone());
        }
    }

    redacted
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_valid_traceparent() {
        let header = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01";

        let context = parse_traceparent(header).expect("valid traceparent");

        assert_eq!(context.trace_id, "0af7651916cd43dd8448eb211c80319c");
        assert_eq!(context.span_id, "b7ad6b7169203331");
        assert!(context.sampled());
    }

    #[test]
    fn reject_invalid_traceparent() {
        assert!(parse_traceparent("invalid").is_err());
        assert!(parse_traceparent("00-123-456-01").is_err());
        assert!(parse_traceparent("01-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01").is_err());
        assert!(parse_traceparent("00-00000000000000000000000000000000-b7ad6b7169203331-01").is_err());
        assert!(parse_traceparent("00-0af7651916cd43dd8448eb211c80319c-0000000000000000-01").is_err());
    }

    #[test]
    fn deterministic_sampler_edges() {
        let always = DeterministicSampler::new(1.0);
        let never = DeterministicSampler::new(0.0);

        let trace_id = "0af7651916cd43dd8448eb211c80319c";

        assert!(always.should_sample(trace_id));
        assert!(!never.should_sample(trace_id));
    }

    #[test]
    fn redacts_secret_attributes() {
        let mut attributes = BTreeMap::new();
        attributes.insert("api_key".to_string(), "abc".to_string());
        attributes.insert("service".to_string(), "test".to_string());

        let redacted = redact_attributes(&attributes);

        assert_eq!(redacted["api_key"], "[REDACTED]");
        assert_eq!(redacted["service"], "test");
    }
}