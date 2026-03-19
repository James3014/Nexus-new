import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from .state_contracts import NexusState

class PolicyManager:
    """📔 Trinity Policy Manager: 處理 Episodic 與 Policy Memory (PHA-050)"""
    
    def __init__(self, project_root: str):
        self.root = Path(project_root)
        self.policy_file = self.root / ".nexus" / "knowledge" / "policy_memory.jsonl"
        self.episode_file = self.root / ".nexus" / "knowledge" / "episodic_memory.jsonl"
        self.policy_file.parent.mkdir(parents=True, exist_ok=True)

    def record_episode(self, state: NexusState):
        """將任務執行軌跡記錄為 Episode"""
        episode = {
            "timestamp": datetime.now().isoformat(),
            "task_id": state.task_id,
            "success": state.health_score > 80,
            "cost": state.total_token_usage,
            "phases": [s.phase for s in state.steps_history],
            "metadata": state.metadata
        }
        with open(self.episode_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(episode) + "\n")

    def propose_policy(self, task_description: str) -> List[Dict[str, Any]]:
        """根據任務描述檢索建議的 Policy"""
        # 初步實作: 基於關鍵字的 Policy 檢索
        policies = []
        if "os" in task_description.lower():
            policies.append({
                "rule_id": "POL-001",
                "condition": "Contains 'os' import",
                "action": "Ensure 'import os' is present in standard headers",
                "confidence": 0.9,
                "status": "validated"
            })
        return policies

    def apply_policy_to_state(self, state: NexusState, task_description: str):
        """將 Policy 注入當前狀態機 (PHA-051)"""
        policies = self.propose_policy(task_description)
        if policies:
            print(f"🎯 [PolicyManager] Applying {len(policies)} policies...")
            state.policy_hit_ids = [p["rule_id"] for p in policies]
            state.policy_applied = True
            # 可擴展: 根據 policy 修改 state.config 或其他參數
