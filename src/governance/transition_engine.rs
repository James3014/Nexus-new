use super::types::FlowState;
use super::error::GovernanceError;
use super::transition_table;

/// ⚙️ Nexus Transition Engine
/// 職責: 執行純粹的狀態轉移計算。不涉及 Blocker 判定或 Receipt 生成。
pub struct TransitionEngine;

impl TransitionEngine {
    pub fn can_transition(from: FlowState, to: FlowState) -> Result<(), GovernanceError> {
        if transition_table::is_allowed(from, to) {
            Ok(())
        } else {
            Err(GovernanceError::IllegalTransition { from, to })
        }
    }

    pub fn next_allowed_states(current: FlowState) -> Vec<FlowState> {
        transition_table::VALID_TRANSITIONS.get(&current)
            .cloned()
            .unwrap_or_default()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_engine_transition_logic() {
        assert!(TransitionEngine::can_transition(FlowState::Plan, FlowState::Execute).is_ok());
        assert!(TransitionEngine::can_transition(FlowState::Plan, FlowState::Verify).is_err());
    }

    #[test]
    fn test_allowed_states_retrieval() {
        let next = TransitionEngine::next_allowed_states(FlowState::Intake);
        assert!(next.contains(&FlowState::Plan));
    }
}
