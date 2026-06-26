from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from nexus.core.state_contracts import NexusState
from nexus.core.state_repository import StateRepository
from nexus.core.metrics_writer import MetricsWriter
from nexus.core.contract_writer import ContractWriter
import logging

logger = logging.getLogger(__name__)

class StateIO:
    """
    💾 Nexus State IO Manager (Facade)
    負責狀態的持久化與讀取，授權給 Repository 與 Writers 處理。
    """
    def __init__(
        self,
        project_root: str,
        state_file: Optional[str] = None,
        run_dir: Optional[str] = None,
    ):
        self.project_root = Path(project_root).resolve()
        self.run_dir = Path(run_dir) if (run_dir and str(run_dir) != "None") else None
        
        # 🧪 [v24.0] Hot-Cache State
        self._hot_state_cache: Dict[str, Any] = {}
        
        if self.run_dir:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            self.state_file = self.run_dir / ".musestate"
        elif state_file:
            self.state_file = Path(state_file)
        else:
            self.state_file = self.project_root / ".nexus" / "misc" / ".musestate"
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            
        self.repository = StateRepository(self.state_file)
        self.metrics_writer = MetricsWriter(self.run_dir / ".nexus_metrics" if self.run_dir else self.state_file.parent / ".nexus_metrics")
        self.contract_writer = ContractWriter(self.run_dir if self.run_dir else self.state_file.parent)

    def save_global_state(self, state: NexusState):
        """🚀 原子級同步：先更新熱快取，再物理落盤 (v24.0 Evolution)"""
        # 1. Update Hot Cache
        self._hot_state_cache[state.task_id] = state
        
        # 2. Physical Persistence (Thread-safe)
        self.repository.save(state)
        self.metrics_writer.write(
            task_id=state.task_id,
            tokens=state.total_token_usage,
            audit_pass=state.audit_pass_count,
            retries=state.retry_count
        )
        logger.debug(f"💾 [StateIO:v24.0] State synced for {state.task_id}")

    def load_global_state(self, task_id: Optional[str] = None) -> NexusState:
        """Back-compat loader used by legacy pipeline/context code."""
        if task_id:
            hot = self._hot_state_cache.get(task_id)
            if hot is not None:
                return hot
        elif self._hot_state_cache:
            # Return latest cached state when caller does not specify task_id.
            return next(reversed(self._hot_state_cache.values()))

        try:
            return self.repository.load()
        except Exception as exc:
            logger.debug("state_load_fallback: %s", exc)
            return NexusState(task_id=task_id or "new-task")

    def write_contract(self, filename: str, data: Any):
        self.contract_writer.write(filename, data)

    def save_checkpoint(self, state: NexusState):
        """📸 物理保存 Agent 心智模型快照"""
        from nexus.core.mental_snapshot import MentalSnapshot
        snapshot = MentalSnapshot(state)
        checkpoint_file = self.state_file.parent / "mind_snapshot.json"
        checkpoint_file.write_text(snapshot.serialize(), encoding="utf-8")
        logger.info(f"🧠 [Mind:Checkpoint] Snapshot preserved to {checkpoint_file}")

    def load_checkpoint(self, state: NexusState) -> bool:
        """📂 從物理快照還原 Agent 心智模型"""
        from nexus.core.mental_snapshot import MentalSnapshot
        checkpoint_file = self.state_file.parent / "mind_snapshot.json"
        
        # Composio P4: 物理回溯觸發
        failure_count = state.metadata.get("phase_failures", 0)
        if isinstance(failure_count, int) and failure_count >= 3:
            logger.warning(f"🚨 [Backtracking] Phase failures >= 3. Rolling back to stable checkpoint...")
            # 實體真值應執行 git_reset(checkpoint_prev)
            state.metadata["phase_failures"] = 0 # 重置
            
        if checkpoint_file.exists():
            try:
                json_str = checkpoint_file.read_text(encoding="utf-8")
                snapshot = MentalSnapshot.deserialize(json_str)
                snapshot.restore_to(state)
                return True
            except Exception as e:
                logger.error(f"❌ [Mind:Restore] Failed to load checkpoint: {e}")
        return False
