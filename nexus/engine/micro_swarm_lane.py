import logging
import json
import hashlib
from typing import List, Dict, Any, Callable
from pathlib import Path
from nexus.engine.battle_swarm import BattleSwarm
from nexus.engine.branch_prompt_builder import BranchPromptBuilder
from nexus.engine.repair_plan import RepairPlan

logger = logging.getLogger(__name__)

class MicroSwarmLane:
    """
    🛡️ MicroSwarmLane: 外掛式受控探索器
    負責協調 2-3 個並行分支的計畫與修補產出。
    """
    def __init__(self, project_root: Path, fan_out: int = 3):
        self.project_root = Path(project_root)
        self.fan_out = min(fan_out, 3)
        self.swarm = BattleSwarm(str(self.project_root), default_workers=self.fan_out)
        self.prompt_builder = BranchPromptBuilder()

    def execute_governed_swarm(
        self, 
        task_id: str,
        task_desc: str,
        base_prompt: str,
        context_payload: str,
        gateway_ask_fn: Callable,
        state_metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        執行受控蜂群。
        gateway_ask_fn: 外部提供的模型調用接口 (task, payload, phase)
        """
        logger.info("🐝 [SwarmLane] Starting Bounded Fan-out for %s (Limit: %d)", task_id, self.fan_out)
        
        # 建立 context 的一致性 Hash 用於驗證
        context_hash = hashlib.sha256(context_payload.encode()).hexdigest()[:8]
        
        def governed_worker(strategy, worktree_path, tid, desc, ctx):
            role_id = strategy["name"]
            logger.info("   ↳ [Swarm:Worker] Branch %s active. Context Hash: %s", role_id, context_hash)
            
            # 1. 構建角色化指令
            branch_prompt = self.prompt_builder.build_branch_prompt(base_prompt, role_id)
            
            # 2. 強制注入 RepairPlan 契約
            plan_contract = RepairPlan()
            payload_with_plan = f"{context_payload}\n\n{plan_contract.format_as_prompt()}"
            
            # 3. 調用模型 (這裡調用外部注入的 gateway_ask_fn)
            data, raw_text = gateway_ask_fn(branch_prompt, payload_with_plan, phase="R")
            
            # 4. 基礎驗證 (Plan Presence)
            plan_present = bool(data.get("touched_symbols") or "RepairPlan" in raw_text)
            
            return {
                "branch_id": role_id,
                "passed": plan_present, # 這裡的 passed 代表符合產出契約
                "score": data.get("confidence", 0.5),
                "data": data,
                "raw_text": raw_text,
                "context_hash": context_hash
            }

        # 設定策略名稱與角色對應
        self.swarm.strategies = [
            {"name": "branch_a", "params": {"temperature": 0.2}},
            {"name": "branch_b", "params": {"temperature": 0.7}},
            {"name": "branch_c", "params": {"temperature": 0.4}}
        ]

        # 觸發 BattleSwarm
        battle_result = self.swarm.trigger_battle(
            task_id=task_id,
            desc=task_desc,
            context=state_metadata,
            execute_fn=governed_worker
        )
        
        return battle_result.get("all_results", [])
