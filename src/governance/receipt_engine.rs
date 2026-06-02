use serde_json::Value;
use super::types::FlowState;
use super::error::GovernanceError;

pub struct ReceiptVerifier;

impl ReceiptVerifier {
    pub fn verify_receipt(receipt: &Value, expected_phase: FlowState) -> Result<(), GovernanceError> {
        let required = vec!["schema_version", "current_state", "transition_reason", "gate_passed"];
        for field in required {
            if receipt.get(field).is_none() {
                return Err(GovernanceError::InvalidReceipt { reason: format!("Missing required field: {}", field) });
            }
        }
        let current_state_str = receipt.get("current_state").and_then(|v| v.as_str()).unwrap_or("Unknown");
        let expected_state_str = format!("{:?}", expected_phase);
        if current_state_str != expected_state_str {
            return Err(GovernanceError::InvalidReceipt { 
                reason: format!("Phase mismatch. Expected {}, got {}", expected_state_str, current_state_str) 
            });
        }
        if receipt.get("gate_passed").and_then(|v| v.as_bool()) != Some(true) {
            return Err(GovernanceError::InvalidReceipt { reason: "Gate passed flag is false".to_string() });
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_receipt_valid() {
        let receipt = json!({
            "schema_version": "v1",
            "current_state": "Execute",
            "transition_reason": "done",
            "gate_passed": true
        });
        assert!(ReceiptVerifier::verify_receipt(&receipt, FlowState::Execute).is_ok());
    }

    #[test]
    fn test_receipt_phase_mismatch() {
        let receipt = json!({
            "schema_version": "v1",
            "current_state": "Plan",
            "transition_reason": "done",
            "gate_passed": true
        });
        let res = ReceiptVerifier::verify_receipt(&receipt, FlowState::Execute);
        assert!(matches!(res, Err(GovernanceError::InvalidReceipt { .. })));
    }
}
