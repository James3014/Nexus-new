use serde::{Deserialize, Serialize};
use sha2::{Sha256, Digest};

/// Canonical JSON serialization: sorted keys, no whitespace, UTF-8.
/// This ensures deterministic hashing across Python and Rust.
pub fn canonical_json(value: &serde_json::Value) -> String {
    // serde_json::to_string with sorted_keys produces canonical form
    let mut map = value.clone();
    canonicalize_recursive(&mut map);
    serde_json::to_string(&map).unwrap_or_default()
}

fn canonicalize_recursive(value: &mut serde_json::Value) {
    match value {
        serde_json::Value::Object(map) => {
            let sorted: std::collections::BTreeMap<String, serde_json::Value> =
                map.iter().map(|(k, v)| (k.clone(), v.clone())).collect();
            *value = serde_json::Value::Object(
                sorted.into_iter().map(|(k, mut v)| {
                    canonicalize_recursive(&mut v);
                    (k, v)
                }).collect()
            );
        }
        serde_json::Value::Array(arr) => {
            for item in arr.iter_mut() {
                canonicalize_recursive(item);
            }
        }
        _ => {}
    }
}

/// Compute SHA-256 hash of canonical JSON payload (excluding "receipt_hash" field).
pub fn compute_receipt_hash(payload: &serde_json::Value) -> String {
    let mut payload_for_hash = payload.clone();
    if let Some(obj) = payload_for_hash.as_object_mut() {
        obj.remove("receipt_hash");
    }
    let canonical = canonical_json(&payload_for_hash);
    let mut hasher = Sha256::new();
    hasher.update(canonical.as_bytes());
    hex::encode(hasher.finalize())
}

#[derive(Serialize, Deserialize, Debug)]
pub struct ReceiptVerificationRequest {
    pub receipt_payload: serde_json::Value,
    pub expected_schema: String,
    pub expected_hash: Option<String>,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct ReceiptVerificationResult {
    pub hash_match: bool,
    pub schema_match: bool,
    pub evidence_complete: bool,
    pub claimability_confirmed: bool,
    pub error_code: Option<String>,
    pub computed_hash: Option<String>,
}

pub struct ReceiptVerifier;

impl ReceiptVerifier {
    /// Verify a receipt with full evidence chain:
    /// 1. Schema match
    /// 2. Canonical JSON hash verification
    /// 3. Evidence completeness (eval_metrics required)
    /// 4. Claimability determination
    pub fn verify(req: ReceiptVerificationRequest) -> ReceiptVerificationResult {
        let payload = req.receipt_payload;

        // 1. Schema check
        let schema_match = match payload.get("schema") {
            Some(s) => s == &req.expected_schema,
            None => false,
        };
        if !schema_match {
            return ReceiptVerificationResult {
                hash_match: false,
                schema_match: false,
                evidence_complete: false,
                claimability_confirmed: false,
                error_code: Some("SCHEMA_MISMATCH".to_string()),
                computed_hash: None,
            };
        }

        // 2. Compute canonical hash
        let computed_hash = compute_receipt_hash(&payload);
        let hash_match = match &req.expected_hash {
            Some(expected) => computed_hash == *expected,
            None => false, // No expected hash → cannot verify
        };

        // 3. Evidence completeness check
        let has_eval_metrics = payload.get("eval_metrics").is_some();
        let has_evidence_bundle = payload.get("evidence_bundle").is_some()
            || payload.get("evidence").is_some();
        let evidence_complete = has_eval_metrics && has_evidence_bundle;

        // 4. Claimability = all gates pass
        let claimability_confirmed = schema_match && hash_match && evidence_complete;

        let error_code = if !schema_match {
            Some("SCHEMA_MISMATCH".to_string())
        } else if !hash_match {
            Some("HASH_MISMATCH".to_string())
        } else if !evidence_complete {
            Some("EVIDENCE_INCOMPLETE".to_string())
        } else {
            None
        };

        ReceiptVerificationResult {
            hash_match,
            schema_match,
            evidence_complete,
            claimability_confirmed,
            error_code,
            computed_hash: Some(computed_hash),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn make_valid_receipt() -> serde_json::Value {
        let mut payload = json!({
            "schema": "S2TStrictDecision.v1",
            "task_id": "test-001",
            "selected_candidate_id": "cand-1",
            "eval_metrics": {
                "pass_rate": 0.95,
                "total_tests": 10
            },
            "evidence_bundle": {
                "receipt_id": "r-001",
                "timestamp": "2026-06-15T00:00:00Z"
            }
        });
        // Compute and attach hash
        let hash = compute_receipt_hash(&payload);
        payload.as_object_mut().unwrap().insert("receipt_hash".to_string(), json!(hash));
        payload
    }

    #[test]
    fn test_valid_receipt_passes_all_gates() {
        let payload = make_valid_receipt();
        let hash = payload.get("receipt_hash").unwrap().as_str().unwrap().to_string();
        let result = ReceiptVerifier::verify(ReceiptVerificationRequest {
            receipt_payload: payload,
            expected_schema: "S2TStrictDecision.v1".to_string(),
            expected_hash: Some(hash),
        });
        assert!(result.schema_match);
        assert!(result.hash_match);
        assert!(result.evidence_complete);
        assert!(result.claimability_confirmed);
        assert!(result.error_code.is_none());
    }

    #[test]
    fn test_tampered_hash_rejects_claim() {
        let payload = make_valid_receipt();
        let result = ReceiptVerifier::verify(ReceiptVerificationRequest {
            receipt_payload: payload,
            expected_schema: "S2TStrictDecision.v1".to_string(),
            expected_hash: Some("0000000000000000000000000000000000000000000000000000000000000000".to_string()),
        });
        assert!(result.schema_match);
        assert!(!result.hash_match);
        assert!(!result.claimability_confirmed);
        assert_eq!(result.error_code.as_deref(), Some("HASH_MISMATCH"));
    }

    #[test]
    fn test_tampered_payload_rejects_claim() {
        let mut payload = make_valid_receipt();
        // Tamper with the payload after hash was computed
        payload.as_object_mut().unwrap().insert("selected_candidate_id".to_string(), json!("TAMPERED"));
        let result = ReceiptVerifier::verify(ReceiptVerificationRequest {
            receipt_payload: payload,
            expected_schema: "S2TStrictDecision.v1".to_string(),
            expected_hash: Some("0000000000000000000000000000000000000000000000000000000000000000".to_string()),
        });
        assert!(!result.claimability_confirmed);
    }

    #[test]
    fn test_schema_mismatch_rejects() {
        let payload = make_valid_receipt();
        let result = ReceiptVerifier::verify(ReceiptVerificationRequest {
            receipt_payload: payload,
            expected_schema: "WrongSchema.v1".to_string(),
            expected_hash: None,
        });
        assert!(!result.schema_match);
        assert!(!result.claimability_confirmed);
        assert_eq!(result.error_code.as_deref(), Some("SCHEMA_MISMATCH"));
    }

    #[test]
    fn test_missing_eval_metrics_rejects_claimability() {
        let mut payload = json!({
            "schema": "S2TStrictDecision.v1",
            "task_id": "test-002"
            // no eval_metrics
        });
        let hash = compute_receipt_hash(&payload);
        payload.as_object_mut().unwrap().insert("receipt_hash".to_string(), json!(hash));
        let result = ReceiptVerifier::verify(ReceiptVerificationRequest {
            receipt_payload: payload,
            expected_schema: "S2TStrictDecision.v1".to_string(),
            expected_hash: Some(hash),
        });
        assert!(result.schema_match);
        assert!(result.hash_match);
        assert!(!result.evidence_complete);
        assert!(!result.claimability_confirmed);
        assert_eq!(result.error_code.as_deref(), Some("EVIDENCE_INCOMPLETE"));
    }

    #[test]
    fn test_missing_evidence_bundle_rejects_claimability() {
        let mut payload = json!({
            "schema": "S2TStrictDecision.v1",
            "task_id": "test-003",
            "eval_metrics": {"pass_rate": 0.9}
            // no evidence_bundle
        });
        let hash = compute_receipt_hash(&payload);
        payload.as_object_mut().unwrap().insert("receipt_hash".to_string(), json!(hash));
        let result = ReceiptVerifier::verify(ReceiptVerificationRequest {
            receipt_payload: payload,
            expected_schema: "S2TStrictDecision.v1".to_string(),
            expected_hash: Some(hash),
        });
        assert!(!result.evidence_complete);
        assert!(!result.claimability_confirmed);
    }

    #[test]
    fn test_canonical_json_deterministic() {
        let payload = json!({"b": 2, "a": 1, "c": {"z": 3, "y": 4}});
        let c1 = canonical_json(&payload);
        let c2 = canonical_json(&payload);
        assert_eq!(c1, c2);
        // Keys should be sorted
        assert!(c1.contains("\"a\":1"));
        assert!(c1.contains("\"b\":2"));
    }

    #[test]
    fn test_compute_hash_deterministic() {
        let payload = json!({"schema": "test.v1", "data": "hello"});
        let h1 = compute_receipt_hash(&payload);
        let h2 = compute_receipt_hash(&payload);
        assert_eq!(h1, h2);
        assert_eq!(h1.len(), 64); // SHA-256 hex = 64 chars
    }

    #[test]
    fn test_hash_excludes_receipt_hash_field() {
        let mut payload = json!({"schema": "test.v1", "data": "hello"});
        let h1 = compute_receipt_hash(&payload);
        payload.as_object_mut().unwrap().insert("receipt_hash".to_string(), json!("should_be_ignored"));
        let h2 = compute_receipt_hash(&payload);
        assert_eq!(h1, h2);
    }

    #[test]
    fn test_missing_schema_rejects() {
        let payload = json!({"task_id": "test"});
        let result = ReceiptVerifier::verify(ReceiptVerificationRequest {
            receipt_payload: payload,
            expected_schema: "any".to_string(),
            expected_hash: None,
        });
        assert!(!result.schema_match);
        assert_eq!(result.error_code.as_deref(), Some("SCHEMA_MISMATCH"));
    }

    #[test]
    fn test_no_expected_hash_rejects() {
        let payload = make_valid_receipt();
        let result = ReceiptVerifier::verify(ReceiptVerificationRequest {
            receipt_payload: payload,
            expected_schema: "S2TStrictDecision.v1".to_string(),
            expected_hash: None,
        });
        assert!(!result.hash_match);
        assert!(!result.claimability_confirmed);
    }
}
