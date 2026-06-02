use super::types::{Route, Decision, FlowState, Confidence};
use super::error::GovernanceError;

pub struct IntentNormalizer;

pub struct NormalizedIntent {
    pub route: Route,
    pub decision: Decision,
    pub phase: FlowState,
    pub confidence: Confidence,
}

impl IntentNormalizer {
    pub fn normalize(raw_output: &str) -> Result<NormalizedIntent, GovernanceError> {
        let clean = raw_output.trim().to_uppercase();
        let parts: Vec<&str> = clean.split(',').collect();
        if parts.len() < 3 {
            return Err(GovernanceError::NormalizationError("Invalid format".into()));
        }
        let mut route = Route::Large;
        let mut decision = Decision::Stop;
        let mut phase = FlowState::Unknown;
        let mut confidence = Confidence::Low;

        for part in parts {
            let kv: Vec<&str> = part.split(':').collect();
            if kv.len() != 2 { continue; }
            match kv[0].trim() {
                "R" => route = match kv[1].trim() { "0" | "LOCAL" => Route::Local, _ => Route::Large },
                "D" => decision = match kv[1].trim() { "0" | "ALLOW" => Decision::Allow, "1" | "REPAIR" => Decision::Repair, "2" | "REJECT" => Decision::Reject, _ => Decision::Stop },
                "P" => phase = match kv[1].trim() { "0" | "S" => FlowState::Intake, "1" | "P" => FlowState::Plan, "2" | "X" | "3" | "D" => FlowState::Execute, "4" | "R" => FlowState::Verify, "5" | "A" | "6" | "C" => FlowState::Close, _ => FlowState::Unknown },
                "C" => confidence = match kv[1].trim() { "0" | "HIGH" => Confidence::High, "1" | "MEDIUM" => Confidence::Medium, _ => Confidence::Low },
                _ => {}
            }
        }
        if decision == Decision::Stop && phase == FlowState::Unknown {
             return Err(GovernanceError::NormalizationError("Unrecognized semantics".into()));
        }
        Ok(NormalizedIntent { route, decision, phase, confidence })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalizer_valid_string() {
        let res = IntentNormalizer::normalize("r:0,d:0,p:1,c:0").unwrap();
        assert_eq!(res.route, Route::Local);
        assert_eq!(res.decision, Decision::Allow);
        assert_eq!(res.phase, FlowState::Plan);
        assert_eq!(res.confidence, Confidence::High);
    }

    #[test]
    fn test_normalizer_rejects_natural_language() {
        let res = IntentNormalizer::normalize("I think we should proceed to Phase R");
        assert!(matches!(res, Err(GovernanceError::NormalizationError(_))));
    }

    #[test]
    fn test_normalizer_falls_back_on_partial_garbage() {
        let res = IntentNormalizer::normalize("r:0, d:invalid, p:99");
        assert!(matches!(res, Err(GovernanceError::NormalizationError(_))));
    }
}
