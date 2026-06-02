use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, Debug)]
pub struct SliceValidationRequest {
    pub outline_text: String,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct SliceValidationResult {
    pub is_valid: bool,
    pub error_code: Option<String>,
    pub detected_patterns: Vec<String>,
}

pub struct VerticalSlicePlanner;

impl VerticalSlicePlanner {
    pub fn validate(req: SliceValidationRequest) -> SliceValidationResult {
        // --- Stage R2-B: Vertical Slice Planner ---
        let text = req.outline_text.to_lowercase();
        let mut patterns = Vec::new();
        let mut error_code = None;

        // 偵測水平切分 (Horizontal Slicing)
        if text.contains("all api") || text.contains("finish backend first") {
            error_code = Some("HORIZONTAL_SLICE_DETECTED".to_string());
            patterns.push("horizontal_slicing".to_string());
        }

        // 偵測缺少驗證
        if !text.contains("verify") && !text.contains("測試") {
             if error_code.is_none() { error_code = Some("NO_VERIFY_COMMAND".to_string()); }
             patterns.push("missing_verification".to_string());
        }

        SliceValidationResult {
            is_valid: error_code.is_none(),
            error_code,
            detected_patterns: patterns,
        }
    }
}
