use chrono::{DateTime, Duration, Utc};
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum TestKitError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("assertion failed at {path}: {message}")]
    Assertion { path: String, message: String },
}

#[derive(Debug)]
pub struct FakeClock {
    current: Mutex<DateTime<Utc>>,
}

impl FakeClock {
    pub fn new(start: DateTime<Utc>) -> Self {
        Self {
            current: Mutex::new(start),
        }
    }

    pub fn now(&self) -> DateTime<Utc> {
        *self.current.lock().expect("fake clock poisoned")
    }

    pub fn advance(&self, duration: Duration) {
        let mut current = self.current.lock().expect("fake clock poisoned");
        *current += duration;
    }

    pub fn set(&self, value: DateTime<Utc>) {
        let mut current = self.current.lock().expect("fake clock poisoned");
        *current = value;
    }
}

pub struct TempWorkspace {
    dir: tempfile::TempDir,
}

impl TempWorkspace {
    pub fn new() -> Result<Self, TestKitError> {
        Ok(Self {
            dir: tempfile::tempdir()?,
        })
    }

    pub fn path(&self) -> &Path {
        self.dir.path()
    }

    pub fn write_file(&self, name: &str, content: &str) -> Result<PathBuf, TestKitError> {
        let path = self.dir.path().join(name);
        fs::write(&path, content)?;
        Ok(path)
    }
}

pub fn load_json_fixture(path: &Path) -> Result<Value, TestKitError> {
    let content = fs::read_to_string(path)?;
    let value = serde_json::from_str(&content)?;
    Ok(value)
}

pub fn assert_json_contains(actual: &Value, expected: &Value) -> Result<(), TestKitError> {
    json_contains(actual, expected, "$")
}

fn json_contains(actual: &Value, expected: &Value, path: &str) -> Result<(), TestKitError> {
    match expected {
        Value::Object(expected_map) => {
            let actual_map = actual.as_object().ok_or_else(|| TestKitError::Assertion {
                path: path.to_string(),
                message: "expected object".to_string(),
            })?;

            for (key, expected_value) in expected_map {
                let child_path = format!("{}.{}", path, key);

                let actual_value =
                    actual_map
                        .get(key)
                        .ok_or_else(|| TestKitError::Assertion {
                            path: child_path.clone(),
                            message: "missing key".to_string(),
                        })?;

                json_contains(actual_value, expected_value, &child_path)?;
            }

            Ok(())
        }
        Value::Array(expected_array) => {
            let actual_array = actual.as_array().ok_or_else(|| TestKitError::Assertion {
                path: path.to_string(),
                message: "expected array".to_string(),
            })?;

            if actual_array.len() != expected_array.len() {
                return Err(TestKitError::Assertion {
                    path: path.to_string(),
                    message: format!(
                        "array length mismatch: actual={} expected={}",
                        actual_array.len(),
                        expected_array.len()
                    ),
                });
            }

            for (index, expected_item) in expected_array.iter().enumerate() {
                let child_path = format!("{}[{}]", path, index);
                json_contains(&actual_array[index], expected_item, &child_path)?;
            }

            Ok(())
        }
        expected_scalar => {
            if actual == expected_scalar {
                Ok(())
            } else {
                Err(TestKitError::Assertion {
                    path: path.to_string(),
                    message: format!("value mismatch: actual={actual} expected={expected_scalar}"),
                })
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::TimeZone;
    use serde_json::json;

    #[test]
    fn fake_clock_advances() {
        let start = Utc.with_ymd_and_hms(2026, 1, 1, 0, 0, 0).unwrap();
        let clock = FakeClock::new(start);

        assert_eq!(clock.now(), start);

        clock.advance(Duration::seconds(30));

        assert_eq!(
            clock.now(),
            Utc.with_ymd_and_hms(2026, 1, 1, 0, 0, 30).unwrap()
        );
    }

    #[test]
    fn temp_workspace_writes_and_loads_json() {
        let workspace = TempWorkspace::new().expect("workspace should be created");

        let path = workspace
            .write_file("fixture.json", r#"{"status":"ok"}"#)
            .expect("fixture should be written");

        let value = load_json_fixture(&path).expect("fixture should load");

        assert_eq!(value["status"], "ok");
    }

    #[test]
    fn json_contains_passes_for_subset() {
        let actual = json!({
            "service": "test",
            "nested": {
                "status": "ok",
                "extra": 1
            }
        });

        let expected = json!({
            "service": "test",
            "nested": {
                "status": "ok"
            }
        });

        assert_json_contains(&actual, &expected).expect("subset should match");
    }

    #[test]
    fn json_contains_fails_for_mismatch() {
        let actual = json!({
            "service": "test",
            "status": "failed"
        });

        let expected = json!({
            "status": "ok"
        });

        assert!(assert_json_contains(&actual, &expected).is_err());
    }
}