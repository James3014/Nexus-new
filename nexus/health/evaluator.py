#!/usr/bin/env python3
import typing
from nexus.health.scoring import HealthScorer
from nexus.health.diagnostics import HealthDiagnostics

class HealthEvaluator:
    """
    💓 健康評估器 (HealthEvaluator)
    整合 HealthScorer 與 HealthDiagnostics，提供統一的系統狀態分析介面內容及對度。
    """
    def __init__(self):
        self.scorer = HealthScorer()
        self.diagnostics = HealthDiagnostics()

    def evaluate_state(self, state: dict) -> typing.Dict[str, typing.Any]:
        """
        對當前狀態執行完整健康評估內容及對等。
        """
        snapshot = self.scorer.apply_snapshot(state)
        return {
            "score": snapshot.get("overall_score", 0.0),
            "snapshot": snapshot,
            "status": "healthy" if snapshot.get("overall_score", 0.0) > 80.0 else "degraded"
        }

    def diagnose_drift(self, state: dict, baseline: dict) -> typing.Dict[str, typing.Any]:
        """
        分析狀態漂移並產出診斷結果內容。
        """
        return self.diagnostics.diagnose(state, baseline)
