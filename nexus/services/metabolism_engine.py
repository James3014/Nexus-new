import json
import logging
import subprocess
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

    def save_checkpoint(self, task_id: str, current_step: str, pending: List[str], terminal_state: str = "PENDING", failure_category: str = "unknown"):
        """💾 建立物理斷點：保存當前堆疊狀態。"""
        self.stack_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "task_id": task_id,
            "last_active_step": current_step,
            "pending_steps": pending,
            "terminal_state": terminal_state,
            "failure_category": failure_category,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        self.stack_path.write_text(json.dumps(data, indent=2))
        logger.info(f"💾 [Checkpoint] Task {task_id} anchored at {current_step} (State: {terminal_state}).")

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

    def build_session_context(self) -> Dict[str, Any]:
        """Build the distill context from real, on-disk session data only.

        Sources (in order): mission state (.nexus/mission.json), metabolism
        checkpoint (task_stack.json). Nothing is invented: when neither exists
        ``goal`` is None and ``context_source`` is ``NONE``.
        """
        sources: List[str] = []
        goal: str | None = None
        done: List[str] = []
        pending: List[str] = []
        try:
            from nexus.core.mission_contracts import NexusMission

            mission = NexusMission.load(self.project_root)
        except Exception:
            mission = None
        if mission is not None and str(mission.objective or "").strip():
            goal = str(mission.objective)
            done = [str(r) for r in (mission.run_history or [])]
            sources.append("mission:.nexus/mission.json")
        checkpoint = self.load_checkpoint()
        if checkpoint.get("task_id"):
            sources.append("checkpoint:.nexus/metabolism/task_stack.json")
            pending = [str(x) for x in (checkpoint.get("pending_steps") or [])]
            if goal is None:
                goal = f"checkpoint task {checkpoint['task_id']} at {checkpoint.get('last_active_step')}"
        return {
            "goal": goal,
            "done": done,
            "todo": pending,
            "errors": [],
            "context_source": "+".join(sources) if sources else "NONE",
        }

    def _git_head(self) -> str | None:
        try:
            out = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        stdout = getattr(out, "stdout", None)
        if getattr(out, "returncode", 1) != 0 or not isinstance(stdout, str):
            return None
        return stdout.strip() or None

    def distill_local(self, session_context: Dict[str, Any] | None = None, p_manager: Any | None = None) -> Dict[str, Any]:
        """Write the local session seed and report honestly what happened.

        No upload is performed: ``tx`` is always None and status is LOCAL_ONLY.
        """
        logger.info("[Metabolism:DISTILLING] Writing local session seed (no upload).")
        if p_manager is not None:
            try:
                from nexus.core.p_loop_manager import PPhase
                p_manager.transition_to(PPhase.P4_METABOLIZE, {"action": "metabolism.distill"})
            except Exception:
                pass
        if session_context is None:
            session_context = self.build_session_context()
        essence = {
            "version": "v23.7-FLEET-COMMAND",
            "last_commit": self._git_head(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "current_objective": session_context.get("goal"),
            "context_source": session_context.get("context_source", "CALLER_SUPPLIED"),
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
        return {
            "status": "LOCAL_ONLY",
            "seed_path": str(seed_path),
            "tx": None,
            "upload": "NOT_PERFORMED",
            "context_source": essence["context_source"],
            "objective": essence["current_objective"],
        }

    def distill(self, session_context: Dict[str, Any], p_manager: Any | None = None) -> str:
        """Compatibility wrapper: writes the local seed and returns its path.

        This no longer returns a (fake) Arweave transaction id; nothing is uploaded.
        """
        return self.distill_local(session_context, p_manager=p_manager)["seed_path"]

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
