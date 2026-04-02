from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging
logger = logging.getLogger(__name__)
from datetime import datetime
from .episode_repository import EpisodeRepository
from .learning_evidence import LearningEvidenceBuilder
from .learning_scorer import LearningScorer
from .policy_metabolizer import PolicyMetabolizer
from .state_contracts import NexusState

class PolicyManager:
    """📔 Trinity Policy Manager: 處理 Episodic 與 Policy Memory (PHA-050)"""
    
    def __init__(self, project_root: str, run_dir: Optional[str] = None):
        self.root = Path(project_root)
        self.run_dir = Path(run_dir) if run_dir else None
        self.episode_repository = EpisodeRepository(str(self.root))
        self.policy_metabolizer = PolicyMetabolizer(
            str(self.root), coordinator=self.episode_repository.coordinator
        )
        # Backward-compatible accessor used by older tests/tools.
        self.episode_file = self.episode_repository.episode_file
        from nexus.services.memory import MemoryService
        self.memory_service = MemoryService(str(self.root), run_dir=str(self.run_dir) if self.run_dir else None)

    def record_episode(self, state: NexusState):
        """將任務執行軌跡記錄為 Episode"""
        evidence = LearningEvidenceBuilder.build(state)
        episode = LearningEvidenceBuilder.build_episode(state, evidence)
        episode["timestamp"] = datetime.now().isoformat()
        self.episode_repository.append(episode)
        state.metadata["memory_lock_wait_last_ms"] = round(
            float(self.episode_repository.coordinator.last_wait_ms), 2
        )
        state.metadata["memory_lock_wait_p95_ms"] = round(
            float(self.episode_repository.coordinator.wait_p95_ms()), 2
        )
        LearningScorer.apply(state, evidence)
        if bool(state.metadata.get("learning_frozen", False)):
            state.metadata["learning_ingest_status"] = "skipped_frozen"
        else:
            try:
                self.memory_service.ingest_episode(episode)
                state.metadata["learning_ingest_status"] = "ingested"
            except Exception:
                state.metadata["learning_ingest_status"] = "ingest_failed"
        self._run_metabolizer(state)

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
        """將 Policy 注入當前狀態機 (PHA-051) + 守則 2: 神經閘門預檢性質性能。"""
        # 🛡️ 守則 2: 接入 v3.2.4 神經哨兵，實現新舊雙軌治理。內容性能分析。
        from nexus.plugins.sentinel_plugin import evaluate_neural_intent
        
        # 🧬 [Neural Reflex] v3.2.4 P1 Track 2: 意圖導通性質分析成果。內容其及性能。
        state.intent = getattr(state, 'intent', task_description or "")
        
        if not evaluate_neural_intent(state.intent):
            state.metadata["neural_veto"] = True # Veto 標記性質分析內容。
            logger.warning(f"[Sentinel V3.2] RISK VETO: {state.intent[:50]}...")
            state.policy_applied = False
            return # 🛡️ 物理其及性質內容攔截：不進行語義檢索。內容性能。
        else:
            state.metadata["neural_veto"] = False

        policies = self.propose_policy(task_description)
        if policies:
            print(f"🎯 [PolicyManager] Semantic hit: {len(policies)} policies found.")
            state.policy_hit_ids = [p["rule_id"] for p in policies]
            state.policy_applied = True

    def _run_metabolizer(self, state: NexusState) -> None:
        metadata = state.metadata
        if bool(metadata.get("sir_veto_metabolizer", False)):
            metadata["metabolizer_status"] = "vetoed"
            return

        interval = int(metadata.get("metabolizer_interval", 5) or 5)
        episode_count = int(metadata.get("episode_count", 0))
        if episode_count <= 0:
            return
        if episode_count % max(1, interval) != 0:
            return

        result = self.policy_metabolizer.metabolize()
        metadata["metabolizer_status"] = "executed"
        metadata["metabolizer_result"] = {
            "scanned": result.scanned,
            "archived": result.archived,
            "active": result.active,
            "memory_health_current": result.memory_health_current,
            "negative_transfer_rate": result.negative_transfer_rate,
            "snapshot_path": str(result.snapshot_path) if result.snapshot_path else None,
            "archive_path": str(result.archive_path),
        }
        metadata.setdefault("memory_health_baseline", 100.0)
        metadata["memory_health_current"] = result.memory_health_current
        metadata["negative_transfer_rate"] = result.negative_transfer_rate
