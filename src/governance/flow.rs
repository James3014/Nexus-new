use crate::governance::types::FlowState;

pub struct TransitionGuard;

impl TransitionGuard {
    pub fn can_transition(from: FlowState, to: FlowState) -> bool {
        if from == to {
            return true;
        }

        match from {
            FlowState::INTAKE => matches!(to, FlowState::CLARIFY | FlowState::OUTLINE | FlowState::PLAN),
            FlowState::CLARIFY => matches!(to, FlowState::OUTLINE | FlowState::RESEARCH | FlowState::ESCALATE),
            FlowState::OUTLINE => matches!(to, FlowState::PLAN | FlowState::RESEARCH | FlowState::REPLAN),
            FlowState::RESEARCH => matches!(to, FlowState::DESIGN | FlowState::OUTLINE | FlowState::PLAN),
            FlowState::PLAN => matches!(to, FlowState::EXECUTE | FlowState::REPLAN | FlowState::HUMAN_REVIEW),
            FlowState::EXECUTE => matches!(to, FlowState::VERIFY | FlowState::ESCALATE),
            FlowState::VERIFY => matches!(to, FlowState::CLOSE | FlowState::REPLAN),
            FlowState::REPLAN => matches!(to, FlowState::PLAN | FlowState::OUTLINE),
            FlowState::HUMAN_REVIEW => matches!(to, FlowState::PLAN | FlowState::CLOSE | FlowState::BLOCKED_POLICY),
            _ => false, // Default fail-closed
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_valid_transitions() {
        assert!(TransitionGuard::can_transition(FlowState::PLAN, FlowState::EXECUTE));
        assert!(TransitionGuard::can_transition(FlowState::INTAKE, FlowState::PLAN));
    }

    #[test]
    fn test_invalid_transitions_blocked() {
        assert!(!TransitionGuard::can_transition(FlowState::PLAN, FlowState::VERIFY)); // Must pass EXECUTE
        assert!(!TransitionGuard::can_transition(FlowState::INTAKE, FlowState::CLOSE)); // Illegal shortcut
    }

    #[test]
    fn test_self_transition() {
        assert!(TransitionGuard::can_transition(FlowState::EXECUTE, FlowState::EXECUTE));
    }
}
