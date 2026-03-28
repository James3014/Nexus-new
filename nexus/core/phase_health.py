from __future__ import annotations

from typing import Any, Dict

from .state_contracts import NexusState
from nexus.health.scoring import HealthScorer, PHASE_WEIGHTS


class PhaseHealthCalculator:
    """Compatibility facade over the unified health scoring service."""

    @staticmethod
    def _calculate(phase: str, signals: Dict[str, Any]) -> float:
        score = HealthScorer._score_phase(phase, {k: float(v) for k, v in signals.items() if isinstance(v, (int, float))})
        return score.score

    @staticmethod
    def calculate_p(signals: Dict[str, Any]) -> float:
        return PhaseHealthCalculator._calculate("P", signals)

    @staticmethod
    def calculate_x(signals: Dict[str, Any]) -> float:
        return PhaseHealthCalculator._calculate("X", signals)

    @staticmethod
    def calculate_d(signals: Dict[str, Any]) -> float:
        return PhaseHealthCalculator._calculate("D", signals)

    @staticmethod
    def calculate_r(signals: Dict[str, Any]) -> float:
        return PhaseHealthCalculator._calculate("R", signals)

    @staticmethod
    def calculate_a(signals: Dict[str, Any]) -> float:
        return PhaseHealthCalculator._calculate("A", signals)

    @staticmethod
    def calculate_c(signals: Dict[str, Any]) -> float:
        return PhaseHealthCalculator._calculate("C", signals)

    @classmethod
    def update_state(cls, state: NexusState):
        """Refresh the single-source-of-truth health snapshot on state."""
        for phase in PHASE_WEIGHTS:
            state.phase_metrics.setdefault(phase, type(state.phase_metrics.get("P"))())
        return HealthScorer.apply_snapshot(state)


class AutoSignalFiller:
    """Legacy no-op shim kept for import compatibility."""

    @staticmethod
    def fill(state: NexusState):
        return state
