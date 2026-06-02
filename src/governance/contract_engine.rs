use serde_json::Value;
use super::types::FlowState;
use super::error::GovernanceError;

pub struct TypedContract;

impl TypedContract {
    pub fn validate_payload(phase: FlowState, payload: &Value) -> Result<(), GovernanceError> {
        let required_fields = match phase {
            FlowState::Execute => vec!["root_cause", "target_modules"],
            FlowState::Verify => vec!["diff", "impact_analysis"],
            FlowState::Plan => vec!["task_breakdown", "acceptance_criteria"],
            _ => vec![],
        };
        for field in required_fields {
            if payload.get(field).is_none() {
                return Err(GovernanceError::MissingField { field: field.to_string() });
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_contract_execute_valid() {
        let payload = json!({"root_cause": "typo", "target_modules": ["main.py"]});
        assert!(TypedContract::validate_payload(FlowState::Execute, &payload).is_ok());
    }

    #[test]
    fn test_contract_execute_missing_field() {
        let payload = json!({"root_cause": "typo"});
        let res = TypedContract::validate_payload(FlowState::Execute, &payload);
        assert_eq!(res, Err(GovernanceError::MissingField { field: "target_modules".to_string() }));
    }
}
