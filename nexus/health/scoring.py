from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from nexus.core.state_contracts import NexusState

from .models import HealthSnapshot, HealthStatus, PhaseScore
from .signals import HealthSignalCollector


PHASE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "P": {"plan_completeness": 0.4, "dependency_validity": 0.4, "spec_clarity": 0.2},
    "X": {"evidence_quality": 0.45, "source_relevance": 0.35, "research_latency": 0.20},
    "D": {"root_cause_confidence": 0.4, "diagnosis_precision": 0.4, "false_positive_rate": 0.2},
    "R": {"fix_success_rate": 0.5, "retry_penalty": 0.3, "scope_drift": 0.2},
    "A": {"regression_pass_rate": 0.5, "side_effect_score": 0.3, "coverage_signal": 0.2},
    "C": {"pattern_reuse_rate": 0.3, "lesson_quality": 0.3, "next_run_hit_rate": 0.4},
}

INVERSE_SIGNALS = {"research_latency", "research_latency_norm", "false_positive_rate", "retry_penalty", "scope_drift"}


class HealthScorer:
    """Build a single health snapshot from explicit signals and outcome metrics."""

    @classmethod
    def build_snapshot(cls, state: NexusState) -> HealthSnapshot:
        signal_map = HealthSignalCollector.collect(state)
        phase_scores = {phase: cls._score_phase(phase, signal_map.get(phase, {})) for phase in PHASE_WEIGHTS}
        phase_average = cls._phase_average(phase_scores)
        outcome_score = cls._outcome_score(state)
        overall_score, reasons = cls._overall_score(state, phase_average, outcome_score)
        confidence = cls._confidence(phase_scores, outcome_score)
        status = cls._status_for_score(overall_score)
        return HealthSnapshot(
            overall_score=overall_score,
            outcome_score=outcome_score,
            phase_average=phase_average,
            confidence=confidence,
            status=status,
            phase_scores=phase_scores,
            reasons=reasons,
        )

    @classmethod
    def apply_snapshot(cls, state: NexusState) -> HealthSnapshot:
        # 1. 基礎快照 (Legacy 邏輯)
        snapshot = cls.build_snapshot(state)
        
        # 2. 應用硬化邏輯 (Hardening Logic)
        plan_density = state.metadata.get("plan_density_score", 1.0)
        thinking_depth = state.metadata.get("thinking_depth_score", 1.0)
        
        # 取得 build_snapshot 產出的各項分數
        overall = snapshot.overall_score
        
        # 若計畫密度低於 0.6，進一步懲罰
        if plan_density < 0.6:
            overall *= 0.4
            
        # 累加思維深度加分
        overall = min(overall + (thinking_depth * 20.0), 120.0)

        # 🎯 治理門檻硬化：若有違規，強制封頂 89.9
        if state.metadata.get("governance_violation_count", 0) > 0:
            overall = min(overall, 89.9)

        # 寫回狀態 (v2.0.0 Schema)
        state.phase_health.health_score = round(overall, 1)
        state.phase_health.pipeline_health = snapshot.phase_average if snapshot.phase_average is not None else overall
        state.phase_health.health_metrics.status = cls._status_for_score(overall)
        state.phase_health.health_metrics.last_check_at = datetime.now()

        # 更新 snapshot 對象 (用於 test 回讀)
        reasons = list(snapshot.reasons)
        if state.metadata.get("governance_violation_count", 0) > 0 and "governance_threshold_enforced" not in reasons:
            reasons.append("governance_threshold_enforced")

        snapshot = dataclasses.replace(
            snapshot,
            overall_score=state.phase_health.health_score,
            status=state.phase_health.health_metrics.status,
            reasons=reasons
        )

        state.metadata["health_snapshot"] = {
            "overall_score": snapshot.overall_score,
            "outcome_score": snapshot.outcome_score,
            "phase_average": snapshot.phase_average,
            "confidence": snapshot.confidence,
            "status": snapshot.status,
            "reasons": snapshot.reasons,
        }
        
        # 同步各階段指標到 phase_health
        for phase, score in snapshot.phase_scores.items():
            if phase in state.phase_health.phase_metrics:
                state.phase_health.phase_metrics[phase].health = score.score
                state.phase_health.phase_metrics[phase].signals = dict(score.signals)
        
        return snapshot

    @staticmethod
    def _score_phase(phase: str, signals: Dict[str, float]) -> PhaseScore:
        weights = PHASE_WEIGHTS[phase]
        total_weight = sum(weights.values())
        present_weight = 0.0
        weighted_sum = 0.0
        for key, weight in weights.items():
            metric_key = key
            if key not in signals and key == "research_latency" and "research_latency_norm" in signals:
                metric_key = "research_latency_norm"
            if metric_key not in signals:
                continue
            value = float(signals[metric_key])
            if metric_key in INVERSE_SIGNALS:
                value = max(0.0, 100.0 - value)
            weighted_sum += value * weight
            present_weight += weight

        if present_weight == 0:
            return PhaseScore(
                phase=phase,
                score=0.0,
                completeness=0.0,
                status="UNKNOWN",
                signals=dict(signals),
                issues=["no_signals"],
            )

        raw_score = weighted_sum / present_weight
        completeness = round(present_weight / total_weight, 2)
        score = round(raw_score * (0.5 + (0.5 * completeness)), 1)
        issues = []
        if completeness < 1.0:
            issues.append("incomplete_signals")
        return PhaseScore(
            phase=phase,
            score=score,
            completeness=completeness,
            status=HealthScorer._status_for_score(score),
            signals=dict(signals),
            issues=issues,
        )

    @staticmethod
    def _phase_average(phase_scores: Dict[str, PhaseScore]) -> Optional[float]:
        active = [score.score for score in phase_scores.values() if score.completeness > 0]
        if not active:
            return None
        return round(sum(active) / len(active), 1)

    @staticmethod
    def _outcome_score(state: NexusState) -> Optional[float]:
        metrics = state.phase_health.health_metrics
        has_outcome_signal = bool(metrics.last_check_at) or any(
            [
                metrics.test_pass_rate,
                metrics.drift_index,
                metrics.error_rate,
                metrics.token_efficiency != 1.0,
                state.audit.audit_pass_count,
                state.tokens.total_usage,
            ]
        )
        if not has_outcome_signal:
            return None

        # 基礎成果評分 (v2)
        base_score = (
            (metrics.test_pass_rate * 40.0)
            + (max(0.0, 1.0 - metrics.drift_index) * 20.0)
            + (max(0.0, 1.0 - metrics.error_rate) * 20.0)
            + (min(1.0, metrics.token_efficiency) * 20.0)
        )

        # 治理懲罰 (Governance Penalty)
        governance_penalty = state.metadata.get("governance_violation_count", 0) * 15.0
        final_score = max(0.0, base_score - governance_penalty)
        return round(final_score, 2)

    @classmethod
    def _overall_score(
        cls,
        state: NexusState,
        phase_average: Optional[float],
        outcome_score: Optional[float],
    ) -> tuple[float, list[str]]:
        reasons: list[str] = []
        if outcome_score is None and phase_average is None:
            return 0.0, ["no_health_signals"]
        if outcome_score is None:
            overall = phase_average or 0.0
        elif phase_average is None:
            overall = outcome_score
        else:
            overall = (outcome_score * 0.7) + (phase_average * 0.3)

        # 治理攔截
        if state.metadata.get("governance_violation_count", 0) > 0:
            overall = min(overall, 89.9)
            reasons.append("governance_threshold_enforced")

        review_status = str(state.metadata.get("last_review_status", "")).upper()
        if review_status in {"REJECTED", "FAILED"}:
            overall = min(overall, 45.0)
            reasons.append(f"review_status:{review_status.lower()}")

        # Token 抓取檢查 (v2.0.0 Schema)
        if outcome_score is not None and state.tokens.total_usage == 0 and state.tokens.capture_status == "unknown":
            overall = min(overall, 60.0)
            reasons.append("missing_token_capture")

        return round(overall, 2), reasons

    @staticmethod
    def _confidence(phase_scores: Dict[str, PhaseScore], outcome_score: Optional[float]) -> float:
        values = [score.completeness for score in phase_scores.values() if score.completeness > 0]
        if outcome_score is not None:
            values.append(1.0)
        if not values:
            return 0.0
        return round(sum(values) / len(values), 2)

    @staticmethod
    def _status_for_score(score: float) -> HealthStatus:
        if score >= 100.0:
            return "HEALTHY"
        if score >= 90.0:
            return "HEALTHY"
        if score >= 50.0:
            return "WARNING"
        if score > 0.0:
            return "CRITICAL"
        return "UNKNOWN"

    @staticmethod
    def calculate_reward(status: str) -> float:
        reward_map = {"healthy": 8.0, "repaired": 12.0, "noop": 0.0, "degraded": -4.0, "failed": -10.0}
        return reward_map.get(str(status), 0.0)

    @staticmethod
    def apply_decay_and_rewards(old_weights: dict, route: list, reward: float, decay: float) -> dict[str, float]:
        new_weights = {}
        for phase in ["P", "X", "D", "R", "A", "C"]:
            base = float(old_weights.get(phase, 0.0) or 0.0) * decay
            if phase in route:
                pos = route.index(phase)
                position_weight = max(0.4, 1.0 - (0.15 * float(pos)))
                base += reward * position_weight
            new_weights[phase] = max(-100.0, min(100.0, round(base, 2)))
        return new_weights
