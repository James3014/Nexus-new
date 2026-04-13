import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class SessionMetabolism:
    """🛡️ Nexus v25.5 Session Metabolism Engine (AutoDream + Checkpoint)."""
    def __init__(self, token_limit: int = 128000):
        self.token_limit = token_limit
        self.threshold = 0.85
        self.project_root = Path(__file__).resolve().parents[2]
        self.stack_path = self.project_root / ".nexus" / "metabolism" / "task_stack.json"

    def save_checkpoint(self, task_id: str, current_step: str, pending: List[str]):
        """💾 建立物理斷點：保存當前堆疊狀態。"""
        self.stack_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "task_id": task_id,
            "last_active_step": current_step,
            "pending_steps": pending,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        self.stack_path.write_text(json.dumps(data, indent=2))
        logger.info(f"💾 [Checkpoint] Task {task_id} anchored at {current_step}.")

    def load_checkpoint(self) -> Dict[str, Any]:
        """🔍 載入斷點：讀取任務堆疊。"""
        if not self.stack_path.exists():
            return {}
        try:
            return json.loads(self.stack_path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    def should_distill(self, token_usage: int) -> bool:
        """Compatibility gate used by legacy metabolism tests."""
        return int(token_usage or 0) >= int(self.token_limit * self.threshold)

    def distill(self, session_context: Dict[str, Any], p_manager: Any | None = None) -> str:
        """📉 語義壓縮：將繁雜的對話提煉為結晶 Seed。"""
        logger.info("🧪 [Metabolism:DISTILLING] Crystallizing session essence...")
        if p_manager is not None:
            try:
                from nexus.core.p_loop_manager import PPhase
                p_manager.transition_to(PPhase.P4_METABOLIZE, {"action": "metabolism.distill"})
            except Exception:
                pass
        essence = {
            "version": "v23.7-FLEET-COMMAND",
            "last_commit": os.popen("git rev-parse --short HEAD").read().strip(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "current_objective": session_context.get("goal", "Continuous Evolution"),
            "completed_tasks": session_context.get("done", []),
            "errors": session_context.get("errors", []),
            "checkpoint": self.load_checkpoint(),
            "active_beliefs": self._get_active_beliefs(),
            "design_specs": self._get_design_specs(),
            "learned_lessons": self._get_recent_lessons()
        }
        seed_path = self.project_root / ".nexus" / "metabolism" / "session_seed.json"
        seed_path.parent.mkdir(parents=True, exist_ok=True)
        with open(seed_path, 'w', encoding='utf-8') as f:
            json.dump(essence, f, indent=2, ensure_ascii=False)
        return f"ar_tx_distilled_{int(datetime.now().timestamp())}"

    def _get_active_beliefs(self) -> list:
        beliefs_path = self.project_root / ".nexusknowledge" / "beliefs.jsonl"
        if not beliefs_path.exists(): return []
        active = []
        with open(beliefs_path, "r", encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                if data.get("confidence", 0) > 0.9:
                    active.append({"id": data.get("belief_id"), "content": data.get("content")})
        return active[-5:]

    def _get_design_specs(self) -> dict:
        design_path = self.project_root / "nexus_wiki_vault" / "99_Schema" / "DESIGN.md"
        if not design_path.exists(): return {}
        return {"atmosphere": "Hardened Industrial", "critical_donts": ["No rounded corners"]}

    def _get_recent_lessons(self) -> list:
        lessons_path = self.project_root / ".codex_lessons.md"
        if not lessons_path.exists(): return []
        return lessons_path.read_text().split("###")[-3:]

metabolism = SessionMetabolism()
