use std::collections::HashMap;
use lazy_static::lazy_static;
use super::types::FlowState;

lazy_static! {
    pub static ref VALID_TRANSITIONS: HashMap<FlowState, Vec<FlowState>> = {
        let mut m = HashMap::new();
        m.insert(FlowState::Intake, vec![FlowState::Clarify, FlowState::Outline, FlowState::Plan]);
        m.insert(FlowState::Clarify, vec![FlowState::Outline, FlowState::Research, FlowState::Escalate]);
        m.insert(FlowState::Outline, vec![FlowState::Plan, FlowState::Research, FlowState::Replan]);
        m.insert(FlowState::Research, vec![FlowState::Design, FlowState::Outline, FlowState::Plan]);
        m.insert(FlowState::Plan, vec![FlowState::Execute, FlowState::Replan, FlowState::HumanReview]);
        m.insert(FlowState::Execute, vec![FlowState::Verify, FlowState::Escalate]);
        m.insert(FlowState::Verify, vec![FlowState::Close, FlowState::Replan]);
        m.insert(FlowState::Replan, vec![FlowState::Plan, FlowState::Outline]);
        m.insert(FlowState::HumanReview, vec![FlowState::Plan, FlowState::Close, FlowState::BlockedPolicy]);
        m
    };
}

pub fn is_allowed(from: FlowState, to: FlowState) -> bool {
    if from == to { return true; }
    if matches!(to, FlowState::Escalate | FlowState::Stop) { return true; }
    VALID_TRANSITIONS.get(&from).map(|list| list.contains(&to)).unwrap_or(false)
}
