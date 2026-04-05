# 🛡️ Nexus Online Wisdom Learner (Bayesian Feedback Loop)
# [ARCH-EVO: v23 WISDOM EDITION LEARNER]

from typing import Dict, Any, List
import json
import numpy as np
from datetime import datetime

class BayesianLearner:
    def __init__(self, stats_path: str = "./nexus_swarm/wisdom/learner_stats.json"):
        self.stats_path = stats_path
        self.pattern_stats = self._load_stats()
    
    def _load_stats(self) -> Dict[str, Any]:
        """從本地存儲載入貝氏參數"""
        try:
            with open(self.stats_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_stats(self):
        """持久化貝氏參數"""
        with open(self.stats_path, 'w') as f:
            json.dump(self.pattern_stats, f, indent=4)

    def _get_pattern_entry(self, pattern_id: str) -> Dict[str, Any]:
        """初始化或返回既存 Pattern 統計項"""
        if pattern_id not in self.pattern_stats:
            self.pattern_stats[pattern_id] = {
                "correct_count": 0,
                "fp_count": 0,
                "missed_count": 0,
                "alpha": 1.0,  # 貝氏先驗 (Beta Distribution)
                "beta": 1.0,
                "confidence": 0.5,
                "bypass_score": 0.0,
                "last_feedback_at": None
            }
        return self.pattern_stats[pattern_id]

    def update_feedback(self, pattern_id: str, feedback_type: str, actor_role: str = "human"):
        """
        核心 貝氏 更新 邏輯 (Hardened for v23):
        - Actor Weighting: admin (1.2), human (1.0), automation (0.5)
        - Snapshot: 每次更新前保留狀態以利回滾
        """
        stats = self._get_pattern_entry(pattern_id)
        
        # 🛡️ Snapshot before update
        snapshot_before = stats.copy()
        
        # 🛡️ Actor weighting
        weight = 1.0
        if actor_role == "admin": weight = 1.2
        elif actor_role == "automation": weight = 0.5
        
        if feedback_type == "correct":
            stats["correct_count"] += 1
            stats["alpha"] += weight
        elif feedback_type == "false_positive":
            stats["fp_count"] += 1
            stats["beta"] += weight
        elif feedback_type == "unsafe_missed":
            stats["missed_count"] += 1
            stats["beta"] += (weight * 2.0) # Unsafe missed weights more heavily
        
        # 🛡️ 後驗機率計算
        total_feedback = stats["alpha"] + stats["beta"]
        stats["confidence"] = float(stats["alpha"] / total_feedback)
        
        # Bypass Score: Based on FP ratio
        support = stats["correct_count"] + stats["fp_count"]
        if support > 0:
            stats["bypass_score"] = float(stats["fp_count"] / support)
        
        stats["last_feedback_at"] = datetime.utcnow().isoformat()
        
        self._save_stats()
        return {
            "pattern_id": pattern_id,
            "status": "updated",
            "snapshot_before": snapshot_before,
            "snapshot_after": stats
        }

    def get_decision_bias(self, pattern_id: str) -> Dict[str, Any]:
        """
        給予決策建議 (Decision Governance):
        - bypass_score > 0.7: 建議為 False Positive Pattern，可自動 Bypass。
        - confidence < 0.3: 建議進行人工審查，系統不穩定。
        """
        stats = self._get_pattern_entry(pattern_id)
        
        recommendation = "review"
        if stats["bypass_score"] > 0.7:
             recommendation = "bypass"
        elif stats["confidence"] > 0.8:
             recommendation = "auto_intercept"
             
        return {
            "pattern_id": pattern_id,
            "bypass_score": stats["bypass_score"],
            "confidence": stats["confidence"],
            "recommendation": recommendation,
            "support": stats["correct_count"] + stats["fp_count"]
        }

if __name__ == "__main__":
    # Unit Test: Learning Convergence
    learner = BayesianLearner("/tmp/learner_test.json")
    pattern = "v22_unsafe_lock_pattern"
    
    print(f"🛡️ Initial Decision Bias: {learner.get_decision_bias(pattern)}")
    
    # 模擬 5 次 False Positive 反饋
    for _ in range(5):
        learner.update_feedback(pattern, "false_positive")
        
    bias = learner.get_decision_bias(pattern)
    print(f"🛡️ After 5 FP Feedbacks: {bias}")
    # 期望結果: bypass_score > 0.7, recommendation = 'bypass'
