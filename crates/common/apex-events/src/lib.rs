use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use thiserror::Error;
use uuid::Uuid;

#[derive(Debug, Error)]
pub enum EventError {
    #[error("invalid event type: {0}")]
    InvalidEventType(String),

    #[error("invalid topic name: {0}")]
    InvalidTopicName(String),

    #[error("invalid event version: {0}")]
    InvalidEventVersion(u32),

    #[error("missing idempotency key")]
    MissingIdempotencyKey,

    #[error("missing producer identity")]
    MissingProducerIdentity,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EventEnvelope {
    pub event_id: Uuid,
    pub event_type: String,
    pub event_version: u32,
    pub occurred_at: DateTime<Utc>,
    pub producer_service: String,
    pub producer_plane: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub correlation_id: Option<Uuid>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub causation_id: Option<Uuid>,
    pub idempotency_key: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trace_id: Option<String>,
    #[serde(default)]
    pub payload: serde_json::Value,
}

impl EventEnvelope {
    pub fn topic(&self) -> String {
        format!("{}.v{}", self.event_type, self.event_version)
    }

    pub fn validate(&self) -> Result<(), EventError> {
        validate_event_type(&self.event_type)?;

        if self.event_version == 0 {
            return Err(EventError::InvalidEventVersion(self.event_version));
        }

        if self.idempotency_key.trim().is_empty() {
            return Err(EventError::MissingIdempotencyKey);
        }

        if self.producer_service.trim().is_empty() || self.producer_plane.trim().is_empty() {
            return Err(EventError::MissingProducerIdentity);
        }

        validate_topic_name(&self.topic())?;

        Ok(())
    }
}

pub fn validate_event_type(value: &str) -> Result<(), EventError> {
    if value.trim().is_empty() {
        return Err(EventError::InvalidEventType(value.to_string()));
    }

    if value.len() > 249 {
        return Err(EventError::InvalidEventType(value.to_string()));
    }

    let segments: Vec<&str> = value.split('.').collect();

    if segments.len() < 3 {
        return Err(EventError::InvalidEventType(value.to_string()));
    }

    for segment in segments {
        if segment.is_empty() {
            return Err(EventError::InvalidEventType(value.to_string()));
        }

        for character in segment.chars() {
            let allowed = character.is_ascii_lowercase()
                || character.is_ascii_digit()
                || character == '-';

            if !allowed {
                return Err(EventError::InvalidEventType(value.to_string()));
            }
        }
    }

    Ok(())
}

pub fn validate_topic_name(value: &str) -> Result<(), EventError> {
    if value.trim().is_empty() {
        return Err(EventError::InvalidTopicName(value.to_string()));
    }

    if value.len() > 249 {
        return Err(EventError::InvalidTopicName(value.to_string()));
    }

    if value.starts_with('.') || value.ends_with('.') {
        return Err(EventError::InvalidTopicName(value.to_string()));
    }

    for character in value.chars() {
        let allowed = character.is_ascii_alphanumeric()
            || character == '.'
            || character == '-'
            || character == '_';

        if !allowed {
            return Err(EventError::InvalidTopicName(value.to_string()));
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::TimeZone;

    fn valid_envelope() -> EventEnvelope {
        EventEnvelope {
            event_id: Uuid::new_v4(),
            event_type: "platform.event-bus.heartbeat".to_string(),
            event_version: 1,
            occurred_at: Utc.with_ymd_and_hms(2026, 1, 1, 0, 0, 0).unwrap(),
            producer_service: "service-framework-core".to_string(),
            producer_plane: "CONTROL".to_string(),
            correlation_id: None,
            causation_id: None,
            idempotency_key: "heartbeat:test".to_string(),
            trace_id: None,
            payload: serde_json::json!({"status":"ok"}),
        }
    }

    #[test]
    fn valid_envelope_passes_validation() {
        let envelope = valid_envelope();

        assert!(envelope.validate().is_ok());
        assert_eq!(
            envelope.topic(),
            "platform.event-bus.heartbeat.v1"
        );
    }

    #[test]
    fn rejects_invalid_event_type() {
        let mut envelope = valid_envelope();
        envelope.event_type = "Invalid.EventType".to_string();

        assert!(envelope.validate().is_err());
    }

    #[test]
    fn rejects_event_type_with_too_few_segments() {
        let mut envelope = valid_envelope();
        envelope.event_type = "platform.heartbeat".to_string();

        assert!(envelope.validate().is_err());
    }

    #[test]
    fn rejects_empty_idempotency_key() {
        let mut envelope = valid_envelope();
        envelope.idempotency_key = "   ".to_string();

        assert!(envelope.validate().is_err());
    }

    #[test]
    fn rejects_zero_event_version() {
        let mut envelope = valid_envelope();
        envelope.event_version = 0;

        assert!(envelope.validate().is_err());
    }
}