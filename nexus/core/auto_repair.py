from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .state_contracts import NexusState
from nexus.health.diagnostics import HealthDiagnostics
from nexus.health.executor import RepairExecutor
from nexus.health.planner import RepairPlanner
from nexus.health.scoring import HealthScorer
from nexus.health.service import SelfHealService


class AutoRepairEngine:
    """Compatibility facade over diagnosis -> plan -> execute."""

    @staticmethod
    def _build_context(state: NexusState, repo_root: Optional[Path] = None):
        root = Path(repo_root or Path.cwd())
        snapshot = HealthScorer.build_snapshot(state)
        diagnosis = HealthDiagnostics.diagnose(state, snapshot)
        plan = RepairPlanner(root).build_plan(diagnosis)
        return root, snapshot, diagnosis, plan

    @classmethod
    def analyze_and_suggest(
        cls,
        state: NexusState,
        repo_root: Optional[Path] = None,
    ) -> List[Dict[str, Any]]:
        _, snapshot, diagnosis, plan = cls._build_context(state, repo_root=repo_root)
        suggestions = []
        for action in plan.actions:
            suggestions.append(
                {
                    "id": action.id,
                    "description": action.description,
                    "reason": action.reason,
                    "priority": action.priority,
                    "action": action.run,
                    "disposition": action.disposition,
                    "verify_commands": list(action.verify_commands),
                    "artifact_paths": list(action.artifact_paths),
                    "diagnosis": asdict(diagnosis),
                    "snapshot": {
                        "overall_score": snapshot.overall_score,
                        "status": snapshot.status,
                        "confidence": snapshot.confidence,
                    },
                }
            )
        state.auto_actions = suggestions
        state.metadata["health_diagnosis"] = asdict(diagnosis)
        state.metadata["health_snapshot"] = {
            "overall_score": snapshot.overall_score,
            "outcome_score": snapshot.outcome_score,
            "phase_average": snapshot.phase_average,
            "confidence": snapshot.confidence,
            "status": snapshot.status,
            "reasons": list(snapshot.reasons),
        }
        return suggestions

    @classmethod
    def execute_repairs(
        cls,
        state: NexusState,
        repo_root: Optional[Path] = None,
        executor: Optional[RepairExecutor] = None,
    ):
        root = Path(repo_root or Path.cwd())
        cls.analyze_and_suggest(state, repo_root=root)
        repair_executor = executor or RepairExecutor(root)
        cycle = SelfHealService(root, executor=repair_executor).run_cycle(state)
        return cycle.execution
