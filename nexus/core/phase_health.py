from typing import Dict, Any
from .state_contracts import PhaseMetric, NexusState

class PhaseHealthCalculator:
    """🧬 Nexus 健康度計算引擎 (PHA-022)"""
    
    @staticmethod
    def calculate_p(signals: Dict[str, Any]) -> float:
        return (0.4 * signals.get("plan_completeness", 0) +
                0.4 * signals.get("dependency_validity", 0) +
                0.2 * signals.get("spec_clarity", 0))

    @staticmethod
    def calculate_x(signals: Dict[str, Any]) -> float:
        latency_norm = signals.get("research_latency_norm", 0)
        return (0.45 * signals.get("evidence_quality", 0) +
                0.35 * signals.get("source_relevance", 0) +
                0.20 * (100 - latency_norm))

    @staticmethod
    def calculate_d(signals: Dict[str, Any]) -> float:
        fpr = signals.get("false_positive_rate", 0)
        return (0.4 * signals.get("root_cause_confidence", 0) +
                0.4 * signals.get("diagnosis_precision", 0) +
                0.2 * (100 - fpr))

    @staticmethod
    def calculate_r(signals: Dict[str, Any]) -> float:
        retry_p = signals.get("retry_penalty", 0)
        drift = signals.get("scope_drift", 0)
        return (0.5 * signals.get("fix_success_rate", 0) +
                0.3 * (100 - retry_p) +
                0.2 * (100 - drift))

    @staticmethod
    def calculate_a(signals: Dict[str, Any]) -> float:
        return (0.5 * signals.get("regression_pass_rate", 0) +
                0.3 * signals.get("side_effect_score", 0) +
                0.2 * signals.get("coverage_signal", 0))

    @staticmethod
    def calculate_c(signals: Dict[str, Any]) -> float:
        return (0.4 * signals.get("pattern_reuse_rate", 0) +
                0.3 * signals.get("lesson_quality", 0) +
                0.3 * signals.get("next_run_hit_rate", 0))

    @classmethod
    def update_state(cls, state: NexusState):
        """主入口：填充信號 -> 計算得分 -> 更新全體健康度"""
        AutoSignalFiller.fill(state)
        
        # 遍歷相容性檢查：state.phase_metrics 可能為 None
        metrics = state.phase_metrics or {}
        for phase, metric in metrics.items():
            calc_func = getattr(cls, f"calculate_{phase.lower()}", None)
            if calc_func:
                metric.health = round(calc_func(metric.signals), 1)
        
        # 計算總分
        active_ph = [m.health for m in metrics.values() if m.health > 0]
        if active_ph:
            state.pipeline_health = round(sum(active_ph) / len(active_ph), 1)
        else:
            state.pipeline_health = 0.0

class AutoSignalFiller:
    @staticmethod
    def fill(state: NexusState):
        """🧬 自動從 NexusState 提取信號 (PHA-001)"""
        metrics = state.phase_metrics or {}
        
        p_metric = metrics.get("P")
        if p_metric:
            p_metric.signals.setdefault("plan_completeness", 100.0)
            p_metric.signals.setdefault("dependency_validity", 90.0)
            p_metric.signals.setdefault("spec_clarity", 80.0)

        d_metric = metrics.get("D")
        if d_metric:
            d_metric.signals.setdefault("root_cause_confidence", 85.0)
            d_metric.signals.setdefault("diagnosis_precision", 90.0)

        r_metric = metrics.get("R")
        if r_metric:
            penalty = min((state.retry_count or 0) * 20, 100)
            r_metric.signals.setdefault("retry_penalty", penalty)
            r_metric.signals.setdefault("fix_success_rate", 100.0 if (state.audit_pass_count or 0) > 0 else 0.0)
