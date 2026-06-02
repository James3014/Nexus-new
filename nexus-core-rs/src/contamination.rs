use serde::{Deserialize, Serialize};
use regex::Regex;

#[derive(Serialize, Deserialize, Debug)]
pub struct ContaminationCheckRequest {
    pub content: String,
    pub level: String,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct ContaminationCheckResult {
    pub passed: bool,
    pub detected_terms: Vec<String>,
}

pub struct ContaminationGuard;

impl ContaminationGuard {
    pub fn check(req: ContaminationCheckRequest) -> ContaminationCheckResult {
        // --- Stage R2-C: Contamination Guard ---
        let design_keywords = vec!["fix", "patch", "implement", "modify", "實作", "修復"];
        let mut detected = Vec::new();

        for kw in design_keywords {
            if req.content.to_lowercase().contains(kw) {
                detected.push(kw.to_string());
            }
        }

        ContaminationCheckResult {
            passed: detected.is_empty(),
            detected_terms: detected,
        }
    }
}
