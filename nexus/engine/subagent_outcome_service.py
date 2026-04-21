from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


logger = logging.getLogger(__name__)


class SubagentOutcomeService:
    """Handle subagent outcome merge + lesson crystallization side effects."""

    def __init__(
        self,
        *,
        project_root: Path,
        subprocess_run: Callable[..., Any] = subprocess.run,
        crystal_cls: Any = None,
    ):
        self.project_root = Path(project_root)
        self.subprocess_run = subprocess_run
        self.crystal_cls = crystal_cls

    def handle(self, payload: dict[str, Any], _state: Any) -> bool:
        task_id = payload.get("taskid", "sub-task")
        passed = bool(payload.get("audit_passed", False))
        worktree = payload.get("worktree")

        logger.info("⚖️ [Nexus:Aggregator] Receiving outcome from %s. Audit: %s", task_id, passed)
        if not passed:
            logger.warning("🚨 [Aggregator:REJECT] Sub-agent %s failed audit. Discarding patch.", task_id)
            return False

        if not self._merge_worktree(worktree, task_id):
            return False
        self._save_lesson(payload, task_id)
        self._append_outcome_log(payload)
        return True

    def _merge_worktree(self, worktree: str | None, task_id: str) -> bool:
        try:
            self.subprocess_run(["git", "merge", worktree], cwd=self.project_root, check=True)
            logger.info("✅ [Aggregator:MERGE] Patch from %s integrated to main chain.", task_id)
            return True
        except Exception:
            logger.error("❌ [Aggregator:MERGE_ERROR] Conflict detected during sub-agent merge.")
            return False

    def _save_lesson(self, payload: dict[str, Any], task_id: str) -> None:
        crystal_cls = self.crystal_cls
        if crystal_cls is None:
            from nexus.core.crystal import Crystal as crystal_cls  # local import for lighter module load

        crystal = crystal_cls(self.project_root)
        lesson_id = f"lesson-{task_id}-{int(datetime.now(timezone.utc).timestamp())}"
        crystal.save_lesson(
            lesson_id=lesson_id,
            skill_id="sub-agent-repair",
            payload=payload,
        )
        logger.info("💎 [Aggregator:CRYSTAL] Lesson %s persisted to LanceDB.", lesson_id)

    def _append_outcome_log(self, payload: dict[str, Any]) -> None:
        log_path = self.project_root / ".nexus" / "metrics" / "skill_outcome_events.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
