import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, UTC

logger = logging.getLogger(__name__)

class ExperimentScheduler:
    """
    🧬 AutoResearch 實驗排程器 (v1.2 Semantic Hardened)
    """
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.experiments_root = (self.workspace / ".nexus" / "experiments").resolve()
        self.experiments_root.mkdir(parents=True, exist_ok=True)
        self._active_candidates: Dict[str, Dict[str, Any]] = {}

    def create_candidate(self, candidate_id: str, hypothesis: str, scope: List[str]) -> Dict[str, Any]:
        candidate_path = self.experiments_root / candidate_id
        candidate_path.mkdir(exist_ok=True)
        info = {
            "id": candidate_id, "hypothesis": hypothesis, "status": "created",
            "modifiable_scope": [str(Path(s)) for s in scope],
            "created_at": datetime.now(UTC).isoformat(),
            "path": str(candidate_path), "metrics": {}
        }
        self._active_candidates[candidate_id] = info
        self._save_state(candidate_id)
        return info

    def validate_write(self, candidate_id: str, file_path: str) -> bool:
        """語義核驗：封殺前綴繞過風險"""
        if candidate_id not in self._active_candidates: return False
        try:
            target_path = (self.workspace / file_path).resolve()
            # 語義檢查：是否真的在 Workspace 下
            if not target_path.is_relative_to(self.workspace):
                logger.error("🚫 [Security] Semantic breach blocked: %s", file_path)
                return False
            rel_target = target_path.relative_to(self.workspace)
            scope = self._active_candidates[candidate_id].get("modifiable_scope", [])
            is_allowed = any(
                str(rel_target) == s or rel_target.is_relative_to(Path(s)) 
                for s in scope
            )
            return is_allowed
        except Exception: return False

    def start_experiment(self, candidate_id: str):
        if candidate_id in self._active_candidates:
            self._active_candidates[candidate_id]["status"] = "running"
            self._save_state(candidate_id)

    def finish_evaluation(self, candidate_id: str, metrics: Dict[str, Any]):
        if candidate_id in self._active_candidates:
            self._active_candidates[candidate_id]["status"] = "evaluated"
            self._active_candidates[candidate_id]["metrics"] = metrics
            self._save_state(candidate_id)

    def _save_state(self, candidate_id: str):
        state_file = self.experiments_root / candidate_id / "state.json"
        with open(state_file, "w") as f:
            json.dump(self._active_candidates[candidate_id], f, indent=2)

    def get_candidate(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        return self._active_candidates.get(candidate_id)
