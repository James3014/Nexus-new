use crate::governance::types::FlowState;

/// 🧪 [NEXUS v2.3] Experimental Adapter Trait
/// 規範實驗性模組（如未來可能的 Matcher / AST Scanner）與生產核心的邊界。
/// 實驗模組「只能」透過此介面建議狀態，不能直接修改。
pub trait ExperimentalLane {
    fn suggest_next_state(&self, input: &str) -> Option<FlowState>;
    fn get_lane_id(&self) -> String;
}

pub struct MatcherMock;

impl ExperimentalLane for MatcherMock {
    fn suggest_next_state(&self, _input: &str) -> Option<FlowState> {
        // 模擬實驗性的 Matcher 邏輯
        Some(FlowState::Research)
    }

    fn get_lane_id(&self) -> String {
        "EXPERIMENTAL_MATCHER_V0.1".into()
    }
}
