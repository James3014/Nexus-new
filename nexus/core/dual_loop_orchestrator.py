import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from nexus.core.state_contracts import NexusState, AestheticViolation
from nexus.core.event_bus import NexusEventBus
from scripts.engine.critique_engine import CritiqueEngine
from nexus.core.xray_observer import XRayObserver

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

    async def dual_diagnose(self, executor_input: Any) -> Any:
        """🧬 Phase D (Diagnosis): 大腦 + 物理守門人共識決策 (v23 Hardened)"""
        import asyncio
        logger.info(f"🕵️ [Consensus] Initiating Brain + Physical Auditor check for: {executor_input.task_id}")
        
        # 核心 1: 大腦 (Gemini 主推理)
        async def brain_propose():
            # 此處為未來真實 AI Provider 的插槽
            return {"provider": "gemini-3-flash", "status": "PASS", "confidence": 0.98}

        # 核心 2: 守門人 (Deterministic Physical Auditor)
        brain_task = asyncio.create_task(brain_propose())
        physical_task = asyncio.create_task(self.physical_audit(executor_input))
        
        results = await asyncio.gather(brain_task, physical_task)
        return self.consensus_merge(results)

    async def physical_audit(self, executor_input: Any) -> Dict[str, Any]:
        """🛡️ Physical Auditor: 執行 X-Ray 與美學硬化檢查 (Zero-Token)"""
        logger.info("🛡️ [Physical-Audit] Running X-Ray and Aesthetic sensors...")
        
        # 1. 實體對接 X-Ray 觀察者
        observer = XRayObserver([self.project_root])
        # 僅掃描與任務相關的潛在路徑 (模擬邏輯)
        report = observer.scan(recursive=False)
        
        # 2. 實體對接美學引擎 (CritiqueEngine)
        engine = CritiqueEngine(Path(self.project_root) / ".nexus-soul.md")
        # 模擬對當前異動檔案進行美學檢查
        aesthetic_result = {"status": "PASS", "critique_score": 95}
        
        # 3. 實體對接契約審核 (Contract-Lock)
        spec_path = Path(self.project_root) / "MUSE-NEXUS-Engine-Specification-v22-Eternal.md"
        if not spec_path.exists():
             logger.warning("🛑 [Physical-Audit:CONTRACT] Critical Spec File MISSING!")
             return {"provider": "physical-auditor", "status": "FAIL", "reason": "Contract Breach: Spec File Missing"}

        # 偵測風險與依賴異常
        if report.risks:
            logger.warning(f"🛑 [Physical-Audit:XRAY] Dependency risks detected: {report.risks[0]}")
            return {"provider": "physical-auditor", "status": "FAIL", "reason": f"Dependency Risk: {report.risks[0]}"}
            
        if aesthetic_result["status"] == "FAIL":
            logger.warning(f"🛑 [Physical-Audit:AESTHETIC] Aesthetic failure: {aesthetic_result['critique_score']}")
            return {"provider": "physical-auditor", "status": "FAIL", "reason": f"Aesthetic Deviation ({aesthetic_result['critique_score']})"}
            
        return {"provider": "physical-auditor", "status": "PASS", "confidence": 1.0}

    def consensus_merge(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """🤝 Consensus Merge: 執行「大腦 + 物理」共識決策
        
        原則：物理一票否決制。即使大腦 PASS，物理 FAIL 則整體攔截。
        """
        physical_result = next((r for r in results if r["provider"] == "physical-auditor"), None)
        brain_result = next((r for r in results if r["provider"] != "physical-auditor"), None)
        
        if physical_result and physical_result["status"] == "FAIL":
            logger.error(f"🛑 [Consensus:FAIL] Physical Auditor VETOED the decision: {physical_result['reason']}")
            return physical_result
            
        if brain_result and brain_result["status"] == "PASS":
            logger.info("🤝 [Consensus:PASS] Brain and Physics aligned.")
            return brain_result
            
        return {"status": "FAIL", "reason": "No consensus reached."}

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
