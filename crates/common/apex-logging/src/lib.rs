use chrono::Utc;
use serde_json::{Map, Value};
use std::collections::BTreeMap;
use std::fmt;
use tracing::field::{Field, Visit};
use tracing::{Event, Subscriber};
use tracing_subscriber::fmt::format::Writer;
use tracing_subscriber::fmt::{FmtContext, FormatEvent, FormatFields};
use tracing_subscriber::registry::LookupSpan;
use tracing_subscriber::EnvFilter;

#[derive(Debug, Clone)]
pub struct LoggingConfig {
    pub service_name: String,
    pub service_version: String,
    pub environment: String,
    pub plane: String,
    pub default_level: String,
}

pub fn init(config: LoggingConfig) {
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new(&config.default_level));

    let layer = tracing_subscriber::fmt::layer()
        .event_format(ApexJsonFormatter { config });

    tracing_subscriber::registry()
        .with(filter)
        .with(layer)
        .init();
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

pub fn redact_json(value: Value) -> Value {
    match value {
        Value::Object(map) => {
            let mut redacted = Map::new();

            for (key, val) in map {
                if is_secret_key(&key) {
                    redacted.insert(key, Value::String("[REDACTED]".to_string()));
                } else {
                    redacted.insert(key, redact_json(val));
                }
            }

            Value::Object(redacted)
        }
        Value::Array(items) => Value::Array(items.into_iter().map(redact_json).collect()),
        other => other,
    }
}

struct FieldVisitor {
    message: Option<String>,
    fields: Map<String, Value>,
}

impl FieldVisitor {
    fn new() -> Self {
        Self {
            message: None,
            fields: Map::new(),
        }
    }
}

impl Visit for FieldVisitor {
    fn record_debug(&mut self, field: &Field, value: &dyn fmt::Debug) {
        let name = field.name();

        let formatted = format!("{value:?}");

        if name == "message" {
            self.message = Some(formatted.trim_matches('"').to_string());
        } else {
            self.fields
                .insert(name.to_string(), Value::String(formatted));
        }
    }

    fn record_str(&mut self, field: &Field, value: &str) {
        let name = field.name();

        if name == "message" {
            self.message = Some(value.to_string());
        } else {
            self.fields
                .insert(name.to_string(), Value::String(value.to_string()));
        }
    }

    fn record_i64(&mut self, field: &Field, value: i64) {
        self.fields
            .insert(field.name().to_string(), Value::from(value));
    }

    fn record_u64(&mut self, field: &Field, value: u64) {
        self.fields
            .insert(field.name().to_string(), Value::from(value));
    }

    fn record_bool(&mut self, field: &Field, value: bool) {
        self.fields
            .insert(field.name().to_string(), Value::from(value));
    }

    fn record_f64(&mut self, field: &Field, value: f64) {
        self.fields
            .insert(field.name().to_string(), Value::from(value));
    }
}

struct ApexJsonFormatter {
    config: LoggingConfig,
}

impl<S, N> FormatEvent<S, N> for ApexJsonFormatter
where
    S: Subscriber + for<'a> LookupSpan<'a>,
    N: for<'a> FormatFields<'a> + 'static,
{
    fn format_event(
        &self,
        _ctx: &FmtContext<'_, S, N>,
        mut writer: Writer<'_>,
        event: &Event<'_>,
    ) -> fmt::Result {
        let mut visitor = FieldVisitor::new();
        event.record(&mut visitor);

        let mut payload = BTreeMap::new();

        payload.insert("ts".to_string(), Value::String(Utc::now().to_rfc3339()));
        payload.insert(
            "level".to_string(),
            Value::String(event.metadata().level().to_string()),
        );
        payload.insert(
            "service".to_string(),
            Value::String(self.config.service_name.clone()),
        );
        payload.insert(
            "service_version".to_string(),
            Value::String(self.config.service_version.clone()),
        );
        payload.insert(
            "environment".to_string(),
            Value::String(self.config.environment.clone()),
        );
        payload.insert(
            "plane".to_string(),
            Value::String(self.config.plane.clone()),
        );
        payload.insert(
            "event".to_string(),
            Value::String(event.metadata().name().to_string()),
        );
        payload.insert(
            "message".to_string(),
            Value::String(visitor.message.unwrap_or_default()),
        );

        let data = Value::Object(visitor.fields);
        payload.insert("data".to_string(), redact_json(data));

        let serialized = serde_json::to_string(&payload).map_err(|_| fmt::Error)?;

        writer.write_str(&serialized)?;
        writer.write_str("\n")?;

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn redacts_secret_keys() {
        let value = json!({
            "broker_api_key": "abc",
            "nested": {
                "password": "hunter2",
                "safe": "visible"
            }
        });

        let redacted = redact_json(value);

        assert_eq!(redacted["broker_api_key"], "[REDACTED]");
        assert_eq!(redacted["nested"]["password"], "[REDACTED]");
        assert_eq!(redacted["nested"]["safe"], "visible");
    }

    #[test]
    fn identifies_secret_keys() {
        assert!(is_secret_key("API_KEY"));
        assert!(is_secret_key("postgres_password"));
        assert!(!is_secret_key("service_name"));
    }
}