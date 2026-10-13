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
        # Latest belief-constraint write status: empty string, "ok" or "unavailable".
        self.last_constraint_write_status: str = ""

    def persist_outcome(self, payload: dict[str, Any]) -> Path:
        log_path = self.project_root / ".nexus" / "metrics" / "skill_outcome_events.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")

        self._archive_to_soul_palace(payload)
        self._record_constraint_outcome(payload)
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

    def _record_constraint_outcome(self, payload: dict[str, Any]) -> None:
        """Feed the failed-outcome-pattern producer (consecutive failures -> forbid belief)."""
        try:
            from nexus.services.belief_constraint_producer import BeliefConstraintProducer

            producer = BeliefConstraintProducer(self.project_root)
            producer.record_outcome(payload)
            self.last_constraint_write_status = producer.last_write_status
        except Exception as e:
            self.last_constraint_write_status = "unavailable"
            logger.warning("⚠️ [BeliefConstraint] Outcome recording failed: %s", e)
