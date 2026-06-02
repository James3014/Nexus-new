use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Hash)]
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
    Stop,
    Unknown,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Decision {
    Allow,
    Repair,
    Reject,
    Stop,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Route {
    Local,
    Large,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Confidence {
    High,
    Medium,
    Low,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BlockerCode {
    CheckpointNotConfirmed,
    HorizontalSliceDetected,
    ResearchContainsDesign,
    UnauthorizedSkip,
    None,
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json;

    #[test]
    fn test_type_stability() {
        let state = FlowState::Research;
        let s = serde_json::to_string(&state).unwrap();
        assert_eq!(s, "\"Research\"");
        
        let d = Decision::Allow;
        assert_eq!(serde_json::to_string(&d).unwrap(), "\"Allow\"");
    }
}
