use super::types::{Route, Decision, FlowState, Confidence};
use super::error::GovernanceError;
use regex::Regex;
use lazy_static::lazy_static;

lazy_static! {
    /// 🛡️ [LangSec] 嚴格標籤識別器
    /// 只允許 k:v 格式，且 key 必須是單一字母 r, d, p, c。
    /// 拒絕任何包含空格、特殊字元或長篇大論的輸入。
    static ref LABEL_REGEX: Regex = Regex::new(r"^[RDPCE]:[A-Z0-9_]+(,[RDPCE]:[A-Z0-9_]+)*$").unwrap();
}

pub struct IntentNormalizer;

pub struct NormalizedIntent {
    pub route: Route,
    pub decision: Decision,
    pub phase: FlowState,
    pub confidence: Confidence,
}

impl IntentNormalizer {
    /// 🛡️ 契約化正規化 (Formal Recognizer)
    /// 1. 執行語法檢查 (Syntactic Check)。
    /// 2. 映射語義枚舉 (Semantic Mapping)。
    /// 3. 若違反文法，100% 拒收。
    pub fn normalize(raw_output: &str) -> Result<NormalizedIntent, GovernanceError> {
        let clean = raw_output.trim().to_uppercase().replace(" ", "");
        
        // [LangSec] Step 1: Recognizer phase - 拒絕非正規輸入
        if !LABEL_REGEX.is_match(&clean) {
            return Err(GovernanceError::NormalizationError(
                format!("Recognizer REJECTED: non-formal grammar detected in '{}'", raw_output)
            ));
        }

        let mut route = Route::Large;
        let mut decision = Decision::Stop;
        let mut phase = FlowState::Unknown;
        let mut confidence = Confidence::Low;

        // [LangSec] Step 2: Semantic mapping
        for part in clean.split(',') {
            let kv: Vec<&str> = part.split(':').collect();
            match kv[0] {
                "R" => route = Self::parse_route(kv[1]),
                "D" => decision = Self::parse_decision(kv[1]),
                "P" => phase = Self::parse_phase(kv[1]),
                "C" => confidence = Self::parse_confidence(kv[1]),
                _ => {}
            }
        }

        Ok(NormalizedIntent { route, decision, phase, confidence })
    }

    fn parse_route(val: &str) -> Route {
        match val { "0" | "LOCAL" => Route::Local, _ => Route::Large }
    }

    fn parse_decision(val: &str) -> Decision {
        match val { "0" | "ALLOW" => Decision::Allow, "1" | "REPAIR" => Decision::Repair, "2" | "REJECT" => Decision::Reject, _ => Decision::Stop }
    }

    fn parse_phase(val: &str) -> FlowState {
        match val {
            "0" | "S" | "INTAKE" => FlowState::Intake,
            "1" | "P" | "PLAN" => FlowState::Plan,
            "2" | "X" | "3" | "D" | "EXECUTE" => FlowState::Execute,
            "4" | "R" | "VERIFY" => FlowState::Verify,
            "5" | "A" | "6" | "C" | "CLOSE" => FlowState::Close,
            _ => FlowState::Unknown,
        }
    }

    fn parse_confidence(val: &str) -> Confidence {
        match val { "0" | "HIGH" => Confidence::High, "1" | "MEDIUM" => Confidence::Medium, _ => Confidence::Low }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_grammar_recognition_ok() {
        assert!(IntentNormalizer::normalize("r:0,d:0,p:1,c:0").is_ok());
    }

    #[test]
    fn test_grammar_recognition_rejects_hallucination() {
        let res = IntentNormalizer::normalize("I see you've provided some input...");
        assert!(res.is_err());
        assert!(res.unwrap_err().to_string().contains("Recognizer REJECTED"));
    }

    #[test]
    fn test_grammar_recognition_rejects_malformed() {
        assert!(IntentNormalizer::normalize("r:0,,d:1").is_err());
        assert!(IntentNormalizer::normalize("r:0:extra").is_err());
    }
}
