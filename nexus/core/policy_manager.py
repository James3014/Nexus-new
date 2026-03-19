import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from .state_contracts import NexusState

class PolicyManager:
    """📔 Trinity Policy Manager: 處理 Episodic 與 Policy Memory (PHA-050)"""
    
    def __init__(self, project_root: str, run_dir: Optional[str] = None):
        self.root = Path(project_root)
        self.run_dir = Path(run_dir) if run_dir else None
        from nexus.services.memory import MemoryService
        self.memory_service = MemoryService(str(self.root), run_dir=str(self.run_dir) if self.run_dir else None)

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
        # 🧪 v9: Episode 紀錄至 MemoryService (未來可直接送入 LanceDB)
        # 目前保留 JSONL 作為 M1 穩定產物
        episode_file = self.root / ".nexus" / "knowledge" / "episodic_memory.jsonl"
        episode_file.parent.mkdir(parents=True, exist_ok=True)
        with open(episode_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(episode) + "\n")

    def propose_policy(self, task_description: str) -> List[Dict[str, Any]]:
        """🔌 Phase M2: 根據任務描述語義檢索建議的 Policy"""
        if not task_description:
            return []
            
        # 🧬 使用 MemoryService 的語義檢索
        results = self.memory_service.semantic_search(task_description, table_name="policy")
        
        policies = []
        for r in results:
            policies.append({
                "rule_id": r["id"],
                "content": r["content"],
                "confidence": r["relevance"],
                "status": "validated" # 假設經檢索出的皆為有效策略
            })
        return policies

    def apply_policy_to_state(self, state: NexusState, task_description: str):
        """將 Policy 注入當前狀態機 (PHA-051)"""
        policies = self.propose_policy(task_description)
        if policies:
            print(f"🎯 [PolicyManager] Semantic hit: {len(policies)} policies found.")
            state.policy_hit_ids = [p["rule_id"] for p in policies]
            state.policy_applied = True
