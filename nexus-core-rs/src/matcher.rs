use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, Debug)]
pub struct MatchRequest {
    pub content: String,
    pub pattern: String,
    pub is_regex: bool,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct MatchResult {
    pub found: bool,
    pub start_idx: Option<usize>,
    pub end_idx: Option<usize>,
}

pub struct Matcher;

impl Matcher {
    pub fn execute(req: MatchRequest) -> MatchResult {
        // --- Stage R5: Matcher Core ---
        // 這裡實作確定性的字面與正則匹配引擎
        if req.is_regex {
            // 這裡未來會引入 regex crate，目前先實作一個簡單的 placeholder 或字面回退
            // 為了保持切片最小化，暫時只做字面匹配
            match req.content.find(&req.pattern) {
                Some(idx) => MatchResult {
                    found: true,
                    start_idx: Some(idx),
                    end_idx: Some(idx + req.pattern.len()),
                },
                None => MatchResult {
                    found: false,
                    start_idx: None,
                    end_idx: None,
                },
            }
        } else {
            match req.content.find(&req.pattern) {
                Some(idx) => MatchResult {
                    found: true,
                    start_idx: Some(idx),
                    end_idx: Some(idx + req.pattern.len()),
                },
                None => MatchResult {
                    found: false,
                    start_idx: None,
                    end_idx: None,
                },
            }
        }
    }
}
