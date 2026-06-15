use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, Debug, PartialEq, Eq, Hash, Clone, Copy)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum FlowState {
    Intake,
    Clarify,
    Outline,
    Research,
    Design,
    Plan,
    Execute,
    Verify,
    Close,
    Replan,
    Escalate,
    HumanReview,
    BlockedBudget,
    BlockedPolicy,
}

/// Authoritative transition matrix.
/// Only explicitly listed transitions are allowed.
/// All undefined transitions fail-closed (return false).
pub struct FlowStateMachine;

impl FlowStateMachine {
    pub fn validate_transition(current: FlowState, next: FlowState) -> bool {
        if current == next {
            return true;
        }

        match current {
            FlowState::Intake => matches!(
                next,
                FlowState::Clarify | FlowState::Outline | FlowState::Plan
            ),
            FlowState::Clarify => matches!(
                next,
                FlowState::Outline | FlowState::Research | FlowState::Escalate
            ),
            FlowState::Outline => matches!(
                next,
                FlowState::Plan | FlowState::Research | FlowState::Replan
            ),
            FlowState::Research => matches!(
                next,
                FlowState::Design | FlowState::Outline | FlowState::Plan
            ),
            FlowState::Design => matches!(next, FlowState::Plan | FlowState::Replan),
            FlowState::Plan => matches!(
                next,
                FlowState::Execute | FlowState::Replan | FlowState::HumanReview
            ),
            FlowState::Execute => matches!(
                next,
                FlowState::Verify | FlowState::Escalate | FlowState::BlockedBudget | FlowState::BlockedPolicy
            ),
            FlowState::Verify => matches!(
                next,
                FlowState::Close | FlowState::Replan | FlowState::Escalate
            ),
            FlowState::Close => false, // Terminal state — no outgoing transitions
            FlowState::Replan => matches!(
                next,
                FlowState::Plan | FlowState::Escalate | FlowState::BlockedBudget | FlowState::BlockedPolicy
            ),
            FlowState::Escalate => matches!(
                next,
                FlowState::HumanReview | FlowState::BlockedPolicy | FlowState::Intake
            ),
            FlowState::HumanReview => matches!(
                next,
                FlowState::Plan | FlowState::Execute | FlowState::Close | FlowState::BlockedPolicy
            ),
            FlowState::BlockedBudget => matches!(
                next,
                FlowState::HumanReview | FlowState::Escalate
            ),
            FlowState::BlockedPolicy => matches!(
                next,
                FlowState::HumanReview | FlowState::Escalate
            ),
        }
    }

    /// Get all legal next states from a given state.
    pub fn legal_transitions(current: FlowState) -> Vec<FlowState> {
        let all_states = [
            FlowState::Intake,
            FlowState::Clarify,
            FlowState::Outline,
            FlowState::Research,
            FlowState::Design,
            FlowState::Plan,
            FlowState::Execute,
            FlowState::Verify,
            FlowState::Close,
            FlowState::Replan,
            FlowState::Escalate,
            FlowState::HumanReview,
            FlowState::BlockedBudget,
            FlowState::BlockedPolicy,
        ];
        all_states
            .iter()
            .filter(|&&s| s != current && Self::validate_transition(current, s))
            .copied()
            .collect()
    }

    /// Check if a state is terminal (no outgoing transitions).
    pub fn is_terminal(state: FlowState) -> bool {
        matches!(state, FlowState::Close)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // ─── Terminal State Tests ───────────────────────────────────────────

    #[test]
    fn test_close_is_terminal() {
        assert!(FlowStateMachine::is_terminal(FlowState::Close));
    }

    #[test]
    fn test_close_has_no_legal_transitions() {
        let transitions = FlowStateMachine::legal_transitions(FlowState::Close);
        assert!(transitions.is_empty());
    }

    #[test]
    fn test_close_to_any_is_invalid() {
        assert!(!FlowStateMachine::validate_transition(FlowState::Close, FlowState::Intake));
        assert!(!FlowStateMachine::validate_transition(FlowState::Close, FlowState::Plan));
        assert!(!FlowStateMachine::validate_transition(FlowState::Close, FlowState::Execute));
    }

    // ─── Self-Transition Tests ──────────────────────────────────────────

    #[test]
    fn test_self_transition_always_valid() {
        let all_states = [
            FlowState::Intake, FlowState::Clarify, FlowState::Outline,
            FlowState::Research, FlowState::Design, FlowState::Plan,
            FlowState::Execute, FlowState::Verify, FlowState::Close,
            FlowState::Replan, FlowState::Escalate, FlowState::HumanReview,
            FlowState::BlockedBudget, FlowState::BlockedPolicy,
        ];
        for state in all_states {
            assert!(
                FlowStateMachine::validate_transition(state, state),
                "Self-transition {:?} -> {:?} should be valid",
                state, state
            );
        }
    }

    // ─── Legal Transition Tests ─────────────────────────────────────────

    #[test]
    fn test_intake_legal_transitions() {
        let legal = FlowStateMachine::legal_transitions(FlowState::Intake);
        assert!(legal.contains(&FlowState::Clarify));
        assert!(legal.contains(&FlowState::Outline));
        assert!(legal.contains(&FlowState::Plan));
        assert_eq!(legal.len(), 3);
    }

    #[test]
    fn test_clarify_legal_transitions() {
        let legal = FlowStateMachine::legal_transitions(FlowState::Clarify);
        assert!(legal.contains(&FlowState::Outline));
        assert!(legal.contains(&FlowState::Research));
        assert!(legal.contains(&FlowState::Escalate));
        assert_eq!(legal.len(), 3);
    }

    #[test]
    fn test_outline_legal_transitions() {
        let legal = FlowStateMachine::legal_transitions(FlowState::Outline);
        assert!(legal.contains(&FlowState::Plan));
        assert!(legal.contains(&FlowState::Research));
        assert!(legal.contains(&FlowState::Replan));
        assert_eq!(legal.len(), 3);
    }

    #[test]
    fn test_research_legal_transitions() {
        let legal = FlowStateMachine::legal_transitions(FlowState::Research);
        assert!(legal.contains(&FlowState::Design));
        assert!(legal.contains(&FlowState::Outline));
        assert!(legal.contains(&FlowState::Plan));
        assert_eq!(legal.len(), 3);
    }

    #[test]
    fn test_design_legal_transitions() {
        let legal = FlowStateMachine::legal_transitions(FlowState::Design);
        assert!(legal.contains(&FlowState::Plan));
        assert!(legal.contains(&FlowState::Replan));
        assert_eq!(legal.len(), 2);
    }

    #[test]
    fn test_plan_legal_transitions() {
        let legal = FlowStateMachine::legal_transitions(FlowState::Plan);
        assert!(legal.contains(&FlowState::Execute));
        assert!(legal.contains(&FlowState::Replan));
        assert!(legal.contains(&FlowState::HumanReview));
        assert_eq!(legal.len(), 3);
    }

    #[test]
    fn test_execute_legal_transitions() {
        let legal = FlowStateMachine::legal_transitions(FlowState::Execute);
        assert!(legal.contains(&FlowState::Verify));
        assert!(legal.contains(&FlowState::Escalate));
        assert!(legal.contains(&FlowState::BlockedBudget));
        assert!(legal.contains(&FlowState::BlockedPolicy));
        assert_eq!(legal.len(), 4);
    }

    #[test]
    fn test_verify_legal_transitions() {
        let legal = FlowStateMachine::legal_transitions(FlowState::Verify);
        assert!(legal.contains(&FlowState::Close));
        assert!(legal.contains(&FlowState::Replan));
        assert!(legal.contains(&FlowState::Escalate));
        assert_eq!(legal.len(), 3);
    }

    #[test]
    fn test_replan_legal_transitions() {
        let legal = FlowStateMachine::legal_transitions(FlowState::Replan);
        assert!(legal.contains(&FlowState::Plan));
        assert!(legal.contains(&FlowState::Escalate));
        assert!(legal.contains(&FlowState::BlockedBudget));
        assert!(legal.contains(&FlowState::BlockedPolicy));
        assert_eq!(legal.len(), 4);
    }

    #[test]
    fn test_escalate_legal_transitions() {
        let legal = FlowStateMachine::legal_transitions(FlowState::Escalate);
        assert!(legal.contains(&FlowState::HumanReview));
        assert!(legal.contains(&FlowState::BlockedPolicy));
        assert!(legal.contains(&FlowState::Intake));
        assert_eq!(legal.len(), 3);
    }

    #[test]
    fn test_human_review_legal_transitions() {
        let legal = FlowStateMachine::legal_transitions(FlowState::HumanReview);
        assert!(legal.contains(&FlowState::Plan));
        assert!(legal.contains(&FlowState::Execute));
        assert!(legal.contains(&FlowState::Close));
        assert!(legal.contains(&FlowState::BlockedPolicy));
        assert_eq!(legal.len(), 4);
    }

    #[test]
    fn test_blocked_budget_legal_transitions() {
        let legal = FlowStateMachine::legal_transitions(FlowState::BlockedBudget);
        assert!(legal.contains(&FlowState::HumanReview));
        assert!(legal.contains(&FlowState::Escalate));
        assert_eq!(legal.len(), 2);
    }

    #[test]
    fn test_blocked_policy_legal_transitions() {
        let legal = FlowStateMachine::legal_transitions(FlowState::BlockedPolicy);
        assert!(legal.contains(&FlowState::HumanReview));
        assert!(legal.contains(&FlowState::Escalate));
        assert_eq!(legal.len(), 2);
    }

    // ─── Illegal Transition Tests (Fail-Closed) ─────────────────────────

    #[test]
    fn test_intake_to_execute_is_invalid() {
        assert!(!FlowStateMachine::validate_transition(FlowState::Intake, FlowState::Execute));
    }

    #[test]
    fn test_intake_to_close_is_invalid() {
        assert!(!FlowStateMachine::validate_transition(FlowState::Intake, FlowState::Close));
    }

    #[test]
    fn test_plan_to_intake_is_invalid() {
        assert!(!FlowStateMachine::validate_transition(FlowState::Plan, FlowState::Intake));
    }

    #[test]
    fn test_execute_to_plan_is_invalid() {
        assert!(!FlowStateMachine::validate_transition(FlowState::Execute, FlowState::Plan));
    }

    #[test]
    fn test_verify_to_execute_is_invalid() {
        assert!(!FlowStateMachine::validate_transition(FlowState::Verify, FlowState::Execute));
    }

    #[test]
    fn test_design_to_execute_is_invalid() {
        assert!(!FlowStateMachine::validate_transition(FlowState::Design, FlowState::Execute));
    }

    #[test]
    fn test_blocked_budget_to_execute_is_invalid() {
        assert!(!FlowStateMachine::validate_transition(FlowState::BlockedBudget, FlowState::Execute));
    }

    #[test]
    fn test_blocked_policy_to_execute_is_invalid() {
        assert!(!FlowStateMachine::validate_transition(FlowState::BlockedPolicy, FlowState::Execute));
    }

    // ─── Full Matrix Exhaustive Test ────────────────────────────────────

    #[test]
    fn test_full_matrix_exhaustive() {
        let all_states = [
            FlowState::Intake, FlowState::Clarify, FlowState::Outline,
            FlowState::Research, FlowState::Design, FlowState::Plan,
            FlowState::Execute, FlowState::Verify, FlowState::Close,
            FlowState::Replan, FlowState::Escalate, FlowState::HumanReview,
            FlowState::BlockedBudget, FlowState::BlockedPolicy,
        ];

        let mut total = 0;
        let mut legal = 0;
        let mut illegal = 0;

        for &from in &all_states {
            for &to in &all_states {
                total += 1;
                let result = FlowStateMachine::validate_transition(from, to);
                if result {
                    legal += 1;
                } else {
                    illegal += 1;
                }
            }
        }

        // 14 states × 14 states = 196 total transitions
        assert_eq!(total, 196);
        // Self-transitions: 14 legal
        // Plus explicitly defined transitions
        assert!(legal > 14, "Should have legal transitions beyond self-loops");
        assert!(illegal > 0, "Should have illegal transitions (fail-closed)");
    }

    // ─── Count Verification ─────────────────────────────────────────────

    #[test]
    fn test_legal_transition_counts_match() {
        // Verify each state has exactly the expected number of legal transitions
        assert_eq!(FlowStateMachine::legal_transitions(FlowState::Intake).len(), 3);
        assert_eq!(FlowStateMachine::legal_transitions(FlowState::Clarify).len(), 3);
        assert_eq!(FlowStateMachine::legal_transitions(FlowState::Outline).len(), 3);
        assert_eq!(FlowStateMachine::legal_transitions(FlowState::Research).len(), 3);
        assert_eq!(FlowStateMachine::legal_transitions(FlowState::Design).len(), 2);
        assert_eq!(FlowStateMachine::legal_transitions(FlowState::Plan).len(), 3);
        assert_eq!(FlowStateMachine::legal_transitions(FlowState::Execute).len(), 4);
        assert_eq!(FlowStateMachine::legal_transitions(FlowState::Verify).len(), 3);
        assert_eq!(FlowStateMachine::legal_transitions(FlowState::Close).len(), 0);
        assert_eq!(FlowStateMachine::legal_transitions(FlowState::Replan).len(), 4);
        assert_eq!(FlowStateMachine::legal_transitions(FlowState::Escalate).len(), 3);
        assert_eq!(FlowStateMachine::legal_transitions(FlowState::HumanReview).len(), 4);
        assert_eq!(FlowStateMachine::legal_transitions(FlowState::BlockedBudget).len(), 2);
        assert_eq!(FlowStateMachine::legal_transitions(FlowState::BlockedPolicy).len(), 2);
    }
}
