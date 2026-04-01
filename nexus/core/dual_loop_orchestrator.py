from pathlib import Path
from typing import Dict, List, Any, Optional
from nexus.core.state_contracts import NexusState, AestheticViolation
from nexus.core.event_bus import NexusEventBus
from scripts.engine.critique_engine import CritiqueEngine

logger = logging.getLogger(__name__)

class IntentViolation(Exception):
    """當 Planner 試圖執行寫入類工具時觸發"""
    pass

class DualLoopOrchestrator:
    """🧬 Nexus v26.0 Dual-Loop 調度器 (Composio AO Dimension 1)
    
    實現 Planner (Outer Loop) 與 Executor (Inner Loop) 的物理分離。
    Planner 負責維持意圖純度與 DAG 生成，Executor 負責並行執行。
    """
    
    PLANNER_TOOL_BLOCKLIST = ["file_write", "git_commit", "shell_exec", "replace_file_content"]

    def __init__(self, project_root):
        self.project_root = project_root
        self.active_shards = {}

    def assert_intent_purity(self, tool_call_name: str):
        """🛡️ Intent Purity Guard: 禁止 Planner 呼叫寫入工具"""
        if tool_call_name in self.PLANNER_TOOL_BLOCKLIST:
            logger.error(f"🛑 Intent Violation: Planner 試圖呼叫 {tool_call_name}")
            raise IntentViolation(f"Planner 禁止呼叫寫入類工具: {tool_call_name}")

    def run_dag_orchestration(self, dag: Dict[str, Any], state: NexusState):
        """執行並行 DAG 任務"""
        logger.info(f"🚀 [Dual-Loop] Starting DAG Orchestration for Task: {state.task_id}")
        
        # 遍歷拓樸排序後的 Shards (模擬實作)
        for shard_id, config in dag.get("shards", {}).items():
            self._execute_shard(shard_id, config, state)

    def validate_aesthetic_integrity(self, file_path: Path):
        """🛡️ Phase A (Audit): 執行美學物理核驗"""
        logger.info(f"🕵️ [Audit] Critiquing file: {file_path.name}...")
        engine = CritiqueEngine(self.project_root / ".nexus-soul.md")
        result = engine.critique_file(file_path)
        
        score = result["critique_score"]
        if result["status"] == "FAIL":
            logger.error(f"🛑 Aesthetic Violation: {file_path.name} 分數為 {score}")
            for issue in result["issues"]:
                logger.error(f"  -> {issue}")
            raise AestheticViolation(f"代碼美學未達標 ({score}/90): {file_path.name}")
        
        logger.info(f"✅ [Audit] {file_path.name} Passed (Score: {score})")
        return result

    def _execute_shard(self, shard_id: str, config: Dict[str, Any], state: NexusState):
        """在隔離的 Worktree/Slot 中執行單一分片"""
        trace_id = config.get("traceid")
        parent_id = config.get("parent_task_id")
        
        logger.info(f"📦 [Executor] Spawning Shard: {shard_id} | Trace: {trace_id}")
        
        # 模擬執行並產出檔案 (此處接線實體工具後會產出真實檔案)
        # 假設產出檔案為 path/to/output.py
        # self.validate_aesthetic_integrity(Path(config.get("output_path")))
        
        # 具現化 EventBus 信號路由
        NexusEventBus.publish("shard_spawned", {
            "shard_id": shard_id,
            "parent_task_id": parent_id,
            "trace_id": trace_id,
            "worktree": config.get("worktree_path")
        })
        
        return True
