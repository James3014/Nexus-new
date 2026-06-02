use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, Debug)]
pub struct ReplayRequest {
    pub task_id: String,
    pub original_result: String,
    pub replay_output: String,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct ReplayResult {
    pub identical: bool,
    pub similarity: f64,
    pub mismatch_summary: Option<String>,
}

pub struct ReplayEngine;

impl ReplayEngine {
    pub fn verify(req: ReplayRequest) -> ReplayResult {
        // --- Stage R2-A: Baseline Replay Engine ---
        let identical = req.original_result.trim() == req.replay_output.trim();
        
        // 簡單的相似度計算 (實作切片)
        let similarity = if identical { 1.0 } else { 0.5 }; 

        ReplayResult {
            identical,
            similarity,
            mismatch_summary: if identical { None } else { Some("OUTPUT_DRIFT_DETECTED".to_string()) },
        }
    }
}
