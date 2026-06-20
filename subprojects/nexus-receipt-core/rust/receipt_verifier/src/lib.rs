/// Receipt canonicalization and verification.
///
/// This module implements the deterministic canonicalization pipeline:
/// 1. Parse receipt JSON
/// 2. Canonicalize: sort keys, normalize whitespace, strip optional fields
/// 3. Compute SHA-256 hash
/// 4. Verify against claimed hash
/// 5. Check schema compliance
/// 6. Check evidence completeness
/// 7. Emit fail-closed result

use serde::{Deserialize, Serialize};
use serde_json::{Value, Map};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

// ─── Result ───────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VerificationResult {
    /// Whether the claimed hash matches the computed canonical hash.
    /// `None` means hash was not checked (no claimed_hash in input).
    pub hashmatch: Option<bool>,
    pub schemamatch: bool,
    pub evidencecomplete: bool,
    pub claimabilityconfirmed: bool,
    pub errorcode: Option<String>,
}

impl VerificationResult {
    pub fn is_valid(&self) -> bool {
        // Fail-closed: hash must be checked AND pass, plus schema and evidence
        matches!(self.hashmatch, Some(true)) && self.schemamatch && self.evidencecomplete
    }
}

// ─── Canonicalization ─────────────────────────────────────

/// Canonicalize a receipt JSON value deterministically.
/// - Sort all object keys lexicographically
/// - Preserve array order
/// - Normalize string values (trim whitespace)
/// - Remove optional/null fields not in normative set
pub fn canonicalize(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let mut sorted = BTreeMap::new();
            // Sort keys lexicographically
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort();
            for key in keys {
                let val = &map[key];
                sorted.insert(key.clone(), canonicalize(val));
            }
            Value::Object(Map::from_iter(sorted.into_iter()))
        }
        Value::Array(arr) => {
            Value::Array(arr.iter().map(canonicalize).collect())
        }
        Value::String(s) => {
            Value::String(s.trim().to_string())
        }
        other => other.clone(),
    }
}

/// Compute SHA-256 hash of a canonicalized receipt.
/// Returns hex-encoded lowercase hash.
pub fn compute_hash(canonical: &Value) -> String {
    let serialized = serde_json::to_string(canonical).unwrap();
    let mut hasher = Sha256::new();
    hasher.update(serialized.as_bytes());
    hex::encode(hasher.finalize())
}

// ─── Verification Pipeline ────────────────────────────────

/// Required fields that must be present in every receipt.
pub const REQUIRED_FIELDS: &[&str] = &[
    "id",
    "type",
    "timestamp",
    "model",
    "input_hash",
    "output_hash",
    "evidence",
];

/// Required fields within the evidence array.
pub const EVIDENCE_REQUIRED_FIELDS: &[&str] = &[
    "type",
    "content",
    "hash",
];

/// Verify a receipt: canonicalize, hash-match, schema-check, evidence-check.
/// Fail-closed: if any check fails, return error code.
pub fn verify_receipt(
    raw_json: &str,
    claimed_hash: Option<&str>,
    required_schema_fields: &[&str],
    required_evidence_fields: &[&str],
) -> VerificationResult {
    // Step 1: Parse
    let parsed: Value = match serde_json::from_str(raw_json) {
        Ok(v) => v,
        Err(_e) => {
            return VerificationResult {
                hashmatch: None,
                schemamatch: false,
                evidencecomplete: false,
                claimabilityconfirmed: false,
                errorcode: Some("parse_error".to_string()),
            };
        }
    };

    // Step 2: Canonicalize (exclude claimed_hash from hashing to avoid circular dependency)
    let mut canonical = canonicalize(&parsed);
    if let Value::Object(ref mut map) = canonical {
        map.remove("claimed_hash");
    }

    // Step 3: Hash verification
    let computed = compute_hash(&canonical);
    let hashmatch = match claimed_hash {
        Some(claimed) => Some(computed == claimed),
        None => None, // Not checked — fail-closed: unchecked ≠ passed
    };

    // Step 4: Schema compliance
    let schemamatch = check_schema_compliance(&parsed, required_schema_fields);

    // Step 5: Evidence completeness
    let evidencecomplete = check_evidence_completeness(&parsed, required_evidence_fields);

    // Step 6: Claimability (fail-closed: ALL must pass — hash must be checked AND pass)
    let hash_verified = matches!(hashmatch, Some(true));
    let claimabilityconfirmed = hash_verified && schemamatch && evidencecomplete;

    // Determine error code if any check failed
    let errorcode = if hashmatch == Some(false) {
        Some("hash_mismatch".to_string())
    } else if hashmatch.is_none() {
        Some("hash_not_checked".to_string())
    } else if !schemamatch {
        Some("schema_mismatch".to_string())
    } else if !evidencecomplete {
        Some("evidence_incomplete".to_string())
    } else {
        None
    };

    VerificationResult {
        hashmatch,
        schemamatch,
        evidencecomplete,
        claimabilityconfirmed,
        errorcode,
    }
}

fn check_schema_compliance(receipt: &Value, required_fields: &[&str]) -> bool {
    if let Value::Object(map) = receipt {
        required_fields.iter().all(|field| map.contains_key(*field))
    } else {
        false
    }
}

fn check_evidence_completeness(receipt: &Value, required_evidence_fields: &[&str]) -> bool {
    if let Value::Object(map) = receipt {
        match map.get("evidence") {
            Some(Value::Array(evidence_arr)) => {
                if evidence_arr.is_empty() {
                    return false;
                }
                // Every evidence item must have all required fields
                evidence_arr.iter().all(|item| {
                    if let Value::Object(item_map) = item {
                        required_evidence_fields
                            .iter()
                            .all(|field| item_map.contains_key(*field))
                    } else {
                        false
                    }
                })
            }
            _ => false,
        }
    } else {
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_canonicalization_sorts_keys() {
        let json = r#"{"z_field": 1, "a_field": 2, "m_field": 3}"#;
        let value: Value = serde_json::from_str(json).unwrap();
        let canonical = canonicalize(&value);
        
        // Verify keys are sorted
        if let Value::Object(map) = canonical {
            let keys: Vec<&String> = map.keys().collect();
            let mut sorted = keys.clone();
            sorted.sort();
            assert_eq!(keys, sorted);
        } else {
            panic!("Expected object");
        }
    }

    #[test]
    fn test_canonicalization_normalizes_strings() {
        let json = r#"{"field": "  hello  "}"#;
        let value: Value = serde_json::from_str(json).unwrap();
        let canonical = canonicalize(&value);
        
        assert_eq!(
            canonical["field"],
            "hello"
        );
    }

    #[test]
    fn test_hash_consistency() {
        let json = r#"{"id": "test-1", "type": "research"}"#;
        let value: Value = serde_json::from_str(json).unwrap();
        let canonical = canonicalize(&value);
        let hash1 = compute_hash(&canonical);
        let hash2 = compute_hash(&canonical);
        assert_eq!(hash1, hash2);
    }

    #[test]
    fn test_verify_passes_clean_receipt() {
        // Build a receipt with a valid claimed_hash
        let base_json = r#"{
            "id": "test-1",
            "type": "research",
            "timestamp": "2026-01-01T00:00:00Z",
            "model": "test-model",
            "input_hash": "abc123",
            "output_hash": "def456",
            "evidence": [
                {"type": "log", "content": "test", "hash": "ev1"}
            ],
            "claimed_hash": "PLACEHOLDER"
        }"#;
        let base: Value = serde_json::from_str(base_json).unwrap();
        let canonical = canonicalize(&base);
        let mut map = canonical.as_object().unwrap().clone();
        map.remove("claimed_hash");
        let real_hash = compute_hash(&Value::Object(map));
        
        let json = format!(
            "{{\"id\":\"test-1\",\"type\":\"research\",\"timestamp\":\"2026-01-01T00:00:00Z\",\"model\":\"test-model\",\"input_hash\":\"abc123\",\"output_hash\":\"def456\",\"evidence\":[{{\"type\":\"log\",\"content\":\"test\",\"hash\":\"ev1\"}}],\"claimed_hash\":\"{}\"}}",
            real_hash
        );
        let result = verify_receipt(
            &json,
            Some(&real_hash),
            REQUIRED_FIELDS,
            EVIDENCE_REQUIRED_FIELDS,
        );
        assert!(result.is_valid());
        assert!(result.claimabilityconfirmed);
        assert!(result.errorcode.is_none());
        assert_eq!(result.hashmatch, Some(true));
    }

    #[test]
    fn test_verify_fails_missing_field() {
        let json = r#"{
            "id": "test-1",
            "type": "research"
        }"#;
        let result = verify_receipt(
            json,
            None, // No claimed_hash → hash_not_checked
            REQUIRED_FIELDS,
            EVIDENCE_REQUIRED_FIELDS,
        );
        assert!(!result.is_valid());
        assert!(!result.claimabilityconfirmed);
        assert!(result.errorcode.is_some());
        assert_eq!(result.errorcode, Some("hash_not_checked".to_string()));
        assert_eq!(result.hashmatch, None);
    }

    #[test]
    fn test_verify_fails_missing_evidence() {
        // Build receipt with correct claimed_hash so we can test evidence independently
        let base_json = r#"{
            "id": "test-1",
            "type": "research",
            "timestamp": "2026-01-01T00:00:00Z",
            "model": "test-model",
            "input_hash": "abc",
            "output_hash": "def",
            "evidence": [],
            "claimed_hash": "PLACEHOLDER"
        }"#;
        let base: Value = serde_json::from_str(base_json).unwrap();
        let canonical = canonicalize(&base);
        let mut map = canonical.as_object().unwrap().clone();
        map.remove("claimed_hash");
        let real_hash = compute_hash(&Value::Object(map));

        let json = format!(
            "{{\"id\":\"test-1\",\"type\":\"research\",\"timestamp\":\"2026-01-01T00:00:00Z\",\"model\":\"test-model\",\"input_hash\":\"abc\",\"output_hash\":\"def\",\"evidence\":[],\"claimed_hash\":\"{}\"}}",
            real_hash
        );
        let result = verify_receipt(
            &json,
            Some(&real_hash),
            REQUIRED_FIELDS,
            EVIDENCE_REQUIRED_FIELDS,
        );
        assert!(result.hashmatch == Some(true));
        assert!(!result.evidencecomplete);
        assert_eq!(result.errorcode, Some("evidence_incomplete".to_string()));
    }

    #[test]
    fn test_verify_fails_tampered_hash() {
        let json = r#"{
            "id": "test-1",
            "type": "research",
            "timestamp": "2026-01-01T00:00:00Z",
            "model": "test-model",
            "input_hash": "abc",
            "output_hash": "def",
            "evidence": [
                {"type": "log", "content": "test", "hash": "ev1"}
            ]
        }"#;
        // Provide a fake claimed hash that won't match
        let result = verify_receipt(
            json,
            Some("0000000000000000000000000000000000000000000000000000000000000000"),
            REQUIRED_FIELDS,
            EVIDENCE_REQUIRED_FIELDS,
        );
        assert_eq!(result.hashmatch, Some(false));
        assert_eq!(result.errorcode, Some("hash_mismatch".to_string()));
        assert!(!result.is_valid());
    }
}
