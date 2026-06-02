use serde_json::Value;
use super::types::{FlowState, BlockerCode};
use super::error::GovernanceError;

pub struct StateValidator;

impl StateValidator {
    pub fn validate_state(phase: FlowState, evidence: &Value) -> Result<(), GovernanceError> {
        match phase {
            FlowState::Plan | FlowState::Execute => {
                if evidence.get("checkpoint_confirmed").and_then(|v| v.as_bool()) != Some(true) {
                    return Err(GovernanceError::StateBlocked { code: BlockerCode::CheckpointNotConfirmed });
                }
            },
            _ => {}
        }
        if let Some(slice_type) = evidence.get("slice_type").and_then(|v| v.as_str()) {
            if slice_type == "horizontal" {
                return Err(GovernanceError::StateBlocked { code: BlockerCode::HorizontalSliceDetected });
            }
        }
        if phase == FlowState::Research && evidence.get("design_artifacts").is_some() {
            return Err(GovernanceError::StateBlocked { code: BlockerCode::ResearchContainsDesign });
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_validator_blocks_missing_checkpoint() {
        let evidence = json!({"checkpoint_confirmed": false});
        let res = StateValidator::validate_state(FlowState::Plan, &evidence);
        assert_eq!(res, Err(GovernanceError::StateBlocked { code: BlockerCode::CheckpointNotConfirmed }));
    }

    #[test]
    fn test_validator_blocks_horizontal_slice() {
        let evidence = json!({"checkpoint_confirmed": true, "slice_type": "horizontal"});
        let res = StateValidator::validate_state(FlowState::Execute, &evidence);
        assert_eq!(res, Err(GovernanceError::StateBlocked { code: BlockerCode::HorizontalSliceDetected }));
    }

    #[test]
    fn test_validator_blocks_research_contains_design() {
        let evidence = json!({"design_artifacts": ["mock.png"]});
        let res = StateValidator::validate_state(FlowState::Research, &evidence);
        assert_eq!(res, Err(GovernanceError::StateBlocked { code: BlockerCode::ResearchContainsDesign }));
    }

    #[test]
    fn test_validator_passes_valid_evidence() {
        let evidence = json!({"checkpoint_confirmed": true, "slice_type": "vertical"});
        let res = StateValidator::validate_state(FlowState::Plan, &evidence);
        assert!(res.is_ok());
    }
}
