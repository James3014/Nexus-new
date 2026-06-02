use serde_json::Value;
use super::types::{FlowState, BlockerCode};
use super::error::GovernanceError;

/// 🚫 Nexus Blocker Engine
/// 職責: 依據政策規則（Policy Rules）判定是否應阻斷流程。
/// 不負責欄位格式檢查。
pub struct BlockerEngine;

impl BlockerEngine {
    pub fn calculate_blockers(phase: FlowState, evidence: &Value) -> Result<(), GovernanceError> {
        // 1. Horizontal Slice 政策性攔截
        if let Some(slice_type) = evidence.get("slice_type").and_then(|v| v.as_str()) {
            if slice_type == "horizontal" {
                return Err(GovernanceError::StateBlocked { code: BlockerCode::HorizontalSliceDetected });
            }
        }

        // 2. 階段內容污染政策
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
    fn test_policy_blocks_horizontal_slice() {
        let evidence = json!({"slice_type": "horizontal"});
        let res = BlockerEngine::calculate_blockers(FlowState::Execute, &evidence);
        assert_eq!(res, Err(GovernanceError::StateBlocked { code: BlockerCode::HorizontalSliceDetected }));
    }
}
