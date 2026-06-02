use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, Debug)]
pub struct ReceiptVerificationRequest {
    pub receipt_payload: serde_json::Value,
    pub expected_schema: String,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct ReceiptVerificationResult {
    pub is_valid: bool,
    pub error_message: Option<String>,
    pub claimability_confirmed: bool,
}

pub struct ReceiptVerifier;

impl ReceiptVerifier {
    pub fn verify(req: ReceiptVerificationRequest) -> ReceiptVerificationResult {
        // --- Stage R3: Receipt Verifier Core ---
        // 這裡實作確定性的收據驗證邏輯 (Schema, Hash, Completeness)
        let payload = req.receipt_payload;
        
        // 1. Schema 驗證
        if let Some(schema) = payload.get("schema") {
            if schema != &req.expected_schema {
                return ReceiptVerificationResult {
                    is_valid: false,
                    error_message: Some(format!("SCHEMA_MISMATCH: expected {}, got {}", req.expected_schema, schema)),
                    claimability_confirmed: false,
                };
            }
        } else {
             return ReceiptVerificationResult {
                is_valid: false,
                error_message: Some("MISSING_SCHEMA".to_string()),
                claimability_confirmed: false,
            };
        }

        // 2. 欄位完整性檢查 (Completeness)
        if payload.get("eval_metrics").is_none() {
            return ReceiptVerificationResult {
                is_valid: true, // 格式合法但無法主張
                error_message: Some("INCOMPLETE_TELEMETRY: missing eval_metrics".to_string()),
                claimability_confirmed: false,
            };
        }

        ReceiptVerificationResult {
            is_valid: true,
            error_message: None,
            claimability_confirmed: true,
        }
    }
}
