use serde::{Deserialize, Serialize};
use std::fs;

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct AstRule {
    pub name: String,
    pub pattern: String,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct AstScanResult {
    pub file_path: String,
    pub matches: std::collections::HashMap<String, usize>,
    pub wall_time_ms: f64,
}

pub struct SinglePassScanner {
    rules: Vec<AstRule>,
}

impl SinglePassScanner {
    pub fn new(rules: Vec<AstRule>) -> Self {
        Self { rules }
    }

    pub fn scan(&self, path: &str) -> AstScanResult {
        let start = std::time::Instant::now();
        let content = fs::read_to_string(path).unwrap_or_default();
        
        let mut match_counts = std::collections::HashMap::new();
        for rule in &self.rules {
            match_counts.insert(rule.name.clone(), 0);
        }

        // --- Stage R2: O(N) Single-Pass State Machine ---
        // 這裡實作一個簡單的高效掃描器，一次走訪完成多規則統計
        let mut word = String::with_capacity(64);
        for c in content.chars() {
            if c.is_alphanumeric() || c == '_' {
                word.push(c);
            } else {
                if !word.is_empty() {
                    for rule in &self.rules {
                        if word == rule.pattern {
                            *match_counts.get_mut(&rule.name).unwrap() += 1;
                        }
                    }
                    word.clear();
                }
            }
        }
        
        let duration = start.elapsed();
        AstScanResult {
            file_path: path.to_string(),
            matches: match_counts,
            wall_time_ms: duration.as_secs_f64() * 1000.0,
        }
    }
}
