use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use thiserror::Error;

// Single-source invariant matrix, embedded verbatim at build time.
const MATRIX_YAML: &str = include_str!("../../../../data/rbac/forbidden_matrix.yaml");
const TEST_VECTORS_JSON: &str = include_str!("../../../../data/rbac/test_vectors.json");

#[derive(Debug, Error)]
pub enum RbacError {
    #[error("matrix parse error: {0}")]
    MatrixParse(String),
    #[error("invalid permission string: {0}")]
    InvalidPermission(String),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EvaluationStatus {
    Granted,
    Unprovisioned,
    InvariantViolation,
}

#[derive(Debug, Clone, Deserialize)]
struct Grammar {
    #[allow(dead_code)]
    format: String,
    #[allow(dead_code)]
    wildcard: String,
    segments: Vec<usize>,
    global_wildcard: String,
}

#[derive(Debug, Clone, Deserialize)]
struct MatrixFile {
    #[allow(dead_code)]
    version: u32,
    grammar: Grammar,
    forbidden: HashMap<String, Vec<String>>,
    restricted_planes: Vec<String>,
}

pub struct RbacMatrix {
    pub grammar: Grammar,
    pub forbidden: HashMap<String, Vec<String>>,
    pub restricted_planes: Vec<String>,
}

impl RbacMatrix {
    pub fn load() -> Result<Self, RbacError> {
        let parsed: MatrixFile =
            serde_yaml::from_str(MATRIX_YAML).map_err(|e| RbacError::MatrixParse(e.to_string()))?;
        Ok(Self {
            grammar: parsed.grammar,
            forbidden: parsed.forbidden,
            restricted_planes: parsed.restricted_planes,
        })
    }

    pub fn sha256() -> String {
        let mut hasher = Sha256::new();
        hasher.update(MATRIX_YAML.as_bytes());
        hex::encode(hasher.finalize())
    }

    pub fn is_restricted(&self, plane: &str) -> bool {
        self.restricted_planes.iter().any(|p| p == plane)
    }

    pub fn forbidden_patterns(&self, plane: &str) -> Vec<String> {
        self.forbidden.get(plane).cloned().unwrap_or_default()
    }
}

/// Validate a permission string against the locked grammar.
/// '*' is valid only as a full segment; 2-3 segments for non-global.
pub fn validate_permission(matrix: &RbacMatrix, perm: &str) -> Result<(), RbacError> {
    let global = &matrix.grammar.global_wildcard;
    if perm == global {
        return Ok(());
    }
    if perm.is_empty() {
        return Err(RbacError::InvalidPermission(perm.to_string()));
    }
    if perm != perm.to_lowercase() {
        return Err(RbacError::InvalidPermission(perm.to_string()));
    }
    let segs: Vec<&str> = perm.split(':').collect();
    let min = matrix.grammar.segments.first().copied().unwrap_or(2);
    let max = matrix.grammar.segments.get(1).copied().unwrap_or(3);
    if segs.len() < min || segs.len() > max {
        return Err(RbacError::InvalidPermission(perm.to_string()));
    }
    for seg in &segs {
        if *seg == "*" {
            continue;
        }
        let ok = !seg.is_empty()
            && seg
                .chars()
                .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_' || c == '-');
        if !ok {
            return Err(RbacError::InvalidPermission(perm.to_string()));
        }
    }
    Ok(())
}

/// Does `pattern` authorize `target`? Full-segment wildcards; a broader grant
/// covers a more specific target. Trailing '*' swallows all deeper segments.
pub fn covers(pattern: &str, target: &str) -> bool {
    if pattern == "*" {
        return true;
    }
    let p: Vec<&str> = pattern.split(':').collect();
    let t: Vec<&str> = target.split(':').collect();
    for (i, seg) in p.iter().enumerate() {
        if *seg == "*" && i == p.len() - 1 {
            return true;
        }
        if i >= t.len() {
            return false;
        }
        if *seg == "*" {
            continue;
        }
        if *seg != t[i] {
            return false;
        }
    }
    true
}

/// Two permissions overlap if either could authorize the other.
pub fn overlaps(a: &str, b: &str) -> bool {
    covers(a, b) || covers(b, a)
}

/// Evaluation-time invariant check (fails closed to deny-all).
pub fn evaluate(
    matrix: &RbacMatrix,
    plane: &str,
    permissions: &[String],
    has_roles: bool,
) -> EvaluationStatus {
    // Fail-closed role-less suppression.
    if !has_roles {
        return EvaluationStatus::Unprovisioned;
    }
    if matrix.is_restricted(plane) {
        for g in permissions {
            // Global wildcard is never permitted on a restricted plane.
            if g == &matrix.grammar.global_wildcard {
                return EvaluationStatus::InvariantViolation;
            }
            for d in matrix.forbidden_patterns(plane) {
                if overlaps(g, &d) {
                    return EvaluationStatus::InvariantViolation;
                }
            }
        }
    }
    EvaluationStatus::Granted
}

/// Request-time authorization with deny-overrides-allow under wildcards.
pub fn authorize(
    matrix: &RbacMatrix,
    plane: &str,
    granted: &[String],
    request: &str,
) -> bool {
    // Deny-overrides-allow for restricted planes.
    if matrix.is_restricted(plane) {
        for d in matrix.forbidden_patterns(plane) {
            if covers(&d, request) {
                return false;
            }
        }
    }
    for g in granted {
        if covers(g, request) {
            return true;
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    fn status_str(s: EvaluationStatus) -> &'static str {
        match s {
            EvaluationStatus::Granted => "GRANTED",
            EvaluationStatus::Unprovisioned => "UNPROVISIONED",
            EvaluationStatus::InvariantViolation => "INVARIANT_VIOLATION",
        }
    }

    #[test]
    fn embedded_matrix_matches_source_file() {
        let source = std::fs::read_to_string("../../../../data/rbac/forbidden_matrix.yaml")
            .expect("source matrix file should exist");
        let mut hasher = Sha256::new();
        hasher.update(source.as_bytes());
        let source_hash = hex::encode(hasher.finalize());
        assert_eq!(RbacMatrix::sha256(), source_hash, "matrix drift detected");
    }

    #[test]
    fn conformance_vectors_match() {
        let matrix = RbacMatrix::load().expect("matrix should load");

        #[derive(Deserialize)]
        struct EvalVec {
            plane: String,
            has_roles: bool,
            permissions: Vec<String>,
            expected_status: String,
        }
        #[derive(Deserialize)]
        struct AuthzVec {
            plane: String,
            granted: Vec<String>,
            request: String,
            expected_allow: bool,
        }
        #[derive(Deserialize)]
        struct Vectors {
            evaluate: Vec<EvalVec>,
            authorize: Vec<EvalAuthz>,
        }
        #[derive(Deserialize)]
        struct EvalAuthz {
            plane: String,
            granted: Vec<String>,
            request: String,
            expected_allow: bool,
        }

        let v: Vectors = serde_json::from_str(TEST_VECTORS_JSON).expect("vectors should parse");

        for case in &v.evaluate {
            let got = status_str(evaluate(&matrix, &case.plane, &case.permissions, case.has_roles));
            assert_eq!(got, case.expected_status, "evaluate vector mismatch: {}", case.expected_status);
        }
        for case in &v.authorize {
            let got = authorize(&matrix, &case.plane, &case.granted, &case.request);
            assert_eq!(got, case.expected_allow, "authorize vector mismatch: {}", case.request);
        }
    }

    #[test]
    fn grammar_rejects_partial_wildcards() {
        let matrix = RbacMatrix::load().unwrap();
        assert!(validate_permission(&matrix, "execution:*").is_ok());
        assert!(validate_permission(&matrix, "execution:modify:OMS-1").is_ok());
        assert!(validate_permission(&matrix, "exec*").is_err());
        assert!(validate_permission(&matrix, "execution:sub*").is_err());
        assert!(validate_permission(&matrix, "Execution:submit").is_err());
        assert!(validate_permission(&matrix, "execution").is_err());
        assert!(validate_permission(&matrix, "*").is_ok());
    }
}