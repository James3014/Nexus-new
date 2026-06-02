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

pub struct FlowStateMachine;

impl FlowStateMachine {
    pub fn validate_transition(current: FlowState, next: FlowState) -> bool {
        if current == next {
            return true;
        }
        
        match current {
            FlowState::Intake => matches!(next, FlowState::Clarify | FlowState::Outline | FlowState::Plan),
            FlowState::Clarify => matches!(next, FlowState::Outline | FlowState::Research | FlowState::Escalate),
            FlowState::Outline => matches!(next, FlowState::Plan | FlowState::Research | FlowState::Replan),
            FlowState::Research => matches!(next, FlowState::Design | FlowState::Outline | FlowState::Plan),
            FlowState::Plan => matches!(next, FlowState::Execute | FlowState::Replan | FlowState::HumanReview),
            FlowState::Execute => matches!(next, FlowState::Verify | FlowState::Escalate),
            FlowState::Verify => matches!(next, FlowState::Close | FlowState::Replan),
            _ => false,
        }
    }
}
