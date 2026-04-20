from pathlib import Path
import json
import os
from nexus.core.state_contracts import NexusState
from nexus.core.config import NexusGlobalConfig

class StateRepository:
    def __init__(self, path: Path):
        self.path = Path(path)
        
    def save(self, state: NexusState):
        json_data = state.model_dump_json()
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json_data + "\n")
            
        # 🛡️ 性能層：定期修剪紀錄以防膨脹
        if self.path.stat().st_size > NexusGlobalConfig.STATE_PRUNE_BYTES:
            self._prune_history()

    def _prune_history(self):
        """僅保留最後 MAX_STATE_HISTORY 條紀錄"""
        if not self.path.exists(): return
        try:
            lines = self.path.read_text(encoding="utf-8").strip().split("\n")
            if len(lines) > NexusGlobalConfig.MAX_STATE_HISTORY:
                pruned = lines[-NexusGlobalConfig.MAX_STATE_HISTORY:]
                self.path.write_text("\n".join(pruned) + "\n", encoding="utf-8")
        except Exception:
            pass # Fail-safe for IO errors during prune
            
    def load(self) -> NexusState:
        if not self.path.exists():
            return NexusState(task_id="new-task")
        with open(self.path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            if not lines:
                return NexusState(task_id="empty")
            return NexusState.model_validate_json(lines[-1].strip())
