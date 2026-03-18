from typing import Dict, Any
from .state_contracts import PhaseMetric, NexusState

class PhaseHealthCalculator:
    @staticmethod
    def calculate_p(signals: Dict[str, Any]) -> float:
        # P.health = 0.4*plan_completeness + 0.4*dependency_validity + 0.2*spec_clarity
        return (0.4 * signals.get("plan_completeness", 0) +
                0.4 * signals.get("dependency_validity", 0) +
                0.2 * signals.get("spec_clarity", 0))

    @staticmethod
    def calculate_x(signals: Dict[str, Any]) -> float:
        # X.health = 0.45*evidence_quality + 0.35*source_relevance + 0.20*(100-research_latency_norm)
        latency_norm = signals.get("research_latency_norm", 0)
        return (0.45 * signals.get("evidence_quality", 0) +
                0.35 * signals.get("source_relevance", 0) +
                0.20 * (100 - latency_norm))

    @staticmethod
    def calculate_d(signals: Dict[str, Any]) -> float:
        # D.health = 0.4*root_cause_confidence + 0.4*diagnosis_precision + 0.2*(100-false_positive_rate)
        fpr = signals.get("false_positive_rate", 0)
        return (0.4 * signals.get("root_cause_confidence", 0) +
                0.4 * signals.get("diagnosis_precision", 0) +
                0.2 * (100 - fpr))

    @staticmethod
    def calculate_r(signals: Dict[str, Any]) -> float:
        # R.health = 0.5*fix_success_rate + 0.3*(100-retry_penalty) + 0.2*(100-scope_drift)
        retry_p = signals.get("retry_penalty", 0)
        drift = signals.get("scope_drift", 0)
        return (0.5 * signals.get("fix_success_rate", 0) +
                0.3 * (100 - retry_p) +
                0.2 * (100 - drift))

    @staticmethod
    def calculate_a(signals: Dict[str, Any]) -> float:
        # A.health = 0.5*regression_pass_rate + 0.3*side_effect_score + 0.2*coverage_signal
        return (0.5 * signals.get("regression_pass_rate", 0) +
                0.3 * signals.get("side_effect_score", 0) +
                0.2 * signals.get("coverage_signal", 0))

    @staticmethod
    def calculate_c(signals: Dict[str, Any]) -> float:
        # C.health = 0.4*pattern_reuse_rate + 0.3*lesson_quality + 0.3*next_run_hit_rate
        return (0.4 * signals.get("pattern_reuse_rate", 0) +
                0.3 * signals.get("lesson_quality", 0) +
                0.3 * signals.get("next_run_hit_rate", 0))

    @classmethod
    def update_state(cls, state: NexusState):
        for phase, metric in state.phase_metrics.items():
            calc_func = getattr(cls, f"calculate_{phase.lower()}", None)
            if calc_func:
                metric.health = round(calc_func(metric.signals), 2)
        
        # Calculate pipeline_health (simple average of valid phases for now)
        active_phase_healths = [m.health for m in state.phase_metrics.values() if m.health > 0]
        if active_phase_healths:
            state.pipeline_health = round(sum(active_phase_healths) / len(active_phase_healths), 2)
        else:
            state.pipeline_health = 0.0
