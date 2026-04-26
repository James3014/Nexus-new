from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


class CrystallizationService:
    """Persist crystallized outcome events and dispatch reporter side effects."""

    def __init__(self, *, project_root: Path, reporter: Any):
        self.project_root = Path(project_root)
        self.reporter = reporter

    def persist_outcome(self, payload: dict[str, Any]) -> Path:
        log_path = self.project_root / ".nexus" / "metrics" / "skill_outcome_events.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")

        self._archive_to_soul_palace(payload)
        self.reporter.report_outcome(payload)
        logger.info("💎 [Crystallize] Outcome persisted for task: %s", payload.get("decision_id"))
        return log_path

    def _archive_to_soul_palace(self, payload: dict[str, Any]) -> None:
        try:
            from scripts.ops.soul_palace_engine import SoulPalaceEngine

            palace = SoulPalaceEngine(self.project_root)
            artifact_content = (
                f"Task {payload.get('task_id')} ({payload.get('skill_id')}): Result={payload.get('passed')}"
            )
            palace.store_knowledge("artifact", artifact_content, layer=2)
        except Exception as e:
            logger.warning("⚠️ [SoulPalace:A] Archiving failed: %s", e)
