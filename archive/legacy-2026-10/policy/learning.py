import json
from pathlib import Path
from typing import Dict, Any, List


class PolicyLearner:
    """
    🧠 Policy Learning Implementation
    負責從歷史執行資料中學習並調整技能權重。
    """

    def __init__(self, memory_path: str = "episodic_memory.jsonl", output_path: str = "policy_updates.json"):
        self.memory_path = Path(memory_path)
        self.output_path = Path(output_path)

    def learn(self):
        """讀取歷史資料並產出權重調整建議。"""
        if not self.memory_path.exists():
            print(f"⚠️ Memory file {self.memory_path} not found.")
            return

        skill_metrics = {}

        with open(self.memory_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    skill = entry.get("selected_skill")
                    if not skill:
                        continue

                    if skill not in skill_metrics:
                        skill_metrics[skill] = {"success_count": 0, "total_count": 0, "total_health": 0.0}

                    skill_metrics[skill]["total_count"] += 1
                    if entry.get("success", False):
                        skill_metrics[skill]["success_count"] += 1
                    
                    skill_metrics[skill]["total_health"] += entry.get("health", 0.0)
                except json.JSONDecodeError:
                    continue

        updates = {"skill_weights": {}}
        
        for skill, stats in skill_metrics.items():
            total = stats["total_count"]
            if total == 0:
                continue
                
            success_rate = stats["success_count"] / total
            avg_health = stats["total_health"] / total
            
            # 權重調整策略:
            # 1. 如果 avg_health < 80, 權重調低 (每低 10 分調低 0.5)
            # 2. 如果 success_rate < 0.8, 權重調低 (調低 1.0)
            adjustment = 0.0
            
            if avg_health < 80.0:
                adjustment -= (80.0 - avg_health) / 20.0
                
            if success_rate < 0.8:
                adjustment -= 1.0
                
            if avg_health > 90.0 and success_rate > 0.95:
                adjustment += 0.5

            if adjustment != 0:
                updates["skill_weights"][skill] = round(adjustment, 2)

        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(updates, f, indent=2)
            
        print(f"✅ Policy updates saved to {self.output_path}")
        return updates


if __name__ == "__main__":
    learner = PolicyLearner()
    learner.learn()
