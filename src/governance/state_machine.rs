use super::types::FlowState;
use super::error::GovernanceError;
use super::transition_table;

pub struct TransitionGuard;

impl TransitionGuard {
    pub fn can_transition(from: FlowState, to: FlowState) -> Result<(), GovernanceError> {
        if transition_table::is_allowed(from, to) {
            Ok(())
        } else {
            Err(GovernanceError::IllegalTransition { from, to })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_valid_transitions_pass() {
        assert!(TransitionGuard::can_transition(FlowState::Plan, FlowState::Execute).is_ok());
        assert!(TransitionGuard::can_transition(FlowState::Intake, FlowState::Plan).is_ok());
        assert!(TransitionGuard::can_transition(FlowState::Execute, FlowState::Execute).is_ok());
    }

    #[test]
    fn test_invalid_transitions_fail_with_typed_error() {
        let res = TransitionGuard::can_transition(FlowState::Plan, FlowState::Verify);
        assert_eq!(res, Err(GovernanceError::IllegalTransition { from: FlowState::Plan, to: FlowState::Verify }));

        let res2 = TransitionGuard::can_transition(FlowState::Intake, FlowState::Close);
        assert_eq!(res2, Err(GovernanceError::IllegalTransition { from: FlowState::Intake, to: FlowState::Close }));
    }
    
    #[test]
    fn test_unknown_state_fails_closed() {
        let res = TransitionGuard::can_transition(FlowState::Unknown, FlowState::Plan);
        assert_eq!(res, Err(GovernanceError::IllegalTransition { from: FlowState::Unknown, to: FlowState::Plan }));
    }
}
