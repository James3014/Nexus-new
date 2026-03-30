from __future__ import annotations

from typing import Dict, List, Optional

from nexus.core.state_contracts import NexusState

from .models import HealthSnapshot, HealthTrigger


class HealthTriggerPolicy:
    """Spec-locked trigger evaluation for autonomous self-healing."""

    PHASE_THRESHOLD = 85.0
    PHASE_STREAK_TARGET = 2
    PIPELINE_THRESHOLD = 88.0
    AUDIT_THRESHOLD = 90.0
    LEARNING_STREAK_TARGET = 3

    @classmethod
    def evaluate_and_record(cls, state: NexusState, snapshot: HealthSnapshot, project_root: "Optional[Path]" = None) -> List[HealthTrigger]:
        triggers: List[HealthTrigger] = []
        streaks = cls._phase_streaks(state)

        for phase, phase_score in snapshot.phase_scores.items():
            if phase_score.completeness <= 0:
                continue
            previous = int(streaks.get(phase, 0))
            if phase_score.score < cls.PHASE_THRESHOLD:
                current = previous + 1
                streaks[phase] = current
                if current >= cls.PHASE_STREAK_TARGET:
                    triggers.append(
                        HealthTrigger(
                            code="phase_health_low",
                            reason=f"Phase {phase} health below {cls.PHASE_THRESHOLD} for {current} rounds.",
                            severity="HIGH",
                            target_phase=phase,
                        )
                    )
            else:
                streaks[phase] = 0

        pipeline_health = snapshot.phase_average if snapshot.phase_average is not None else snapshot.overall_score
        if snapshot.confidence >= 0.35 and pipeline_health < cls.PIPELINE_THRESHOLD:
            triggers.append(
                HealthTrigger(
                    code="pipeline_health_low",
                    reason=f"Pipeline health {pipeline_health:.1f} below {cls.PIPELINE_THRESHOLD}.",
                    severity="HIGH",
                )
            )

        audit_score = snapshot.phase_scores.get("A")
        audit_regression_failed = False
        if audit_score and audit_score.completeness > 0:
            regression_pass_rate = audit_score.signals.get("regression_pass_rate")
            if regression_pass_rate is not None:
                audit_regression_failed = float(regression_pass_rate) < 100.0
            if audit_score.score < cls.AUDIT_THRESHOLD and audit_regression_failed:
                triggers.append(
                    HealthTrigger(
                        code="audit_regression_fail",
                        reason="Audit health below 90 with regression fail signal.",
                        severity="HIGH",
                        target_phase="A",
                    )
                )

        learning_velocity = float(state.learning_velocity or 0.0)
        learning_streak = int(state.metadata.get("learning_velocity_non_positive_streak", 0))
        if learning_velocity <= 0.0:
            learning_streak += 1
        else:
            learning_streak = 0
        state.metadata["learning_velocity_non_positive_streak"] = learning_streak

        if learning_streak >= cls.LEARNING_STREAK_TARGET:
            triggers.append(
                HealthTrigger(
                    code="learning_velocity_stalled",
                    reason=f"Learning velocity <= 0 for {learning_streak} rounds.",
                    severity="MEDIUM",
                )
            )

        if project_root is not None:
            from nexus.governance.learning_gate import evaluate_learning_gate
            run_dir = project_root / ".nexus" / "runs" / state.task_id
            gate_result = evaluate_learning_gate(run_dir, project_root)
            if not gate_result.passed:
                state.trust_level = "restricted"
                triggers.append(
                    HealthTrigger(
                        code="learning_gate_failed",
                        reason=f"Learning gate failed: {', '.join(gate_result.failure_reasons)}",
                        severity="MEDIUM",
                    )
                )

        cls._record(state, triggers, pipeline_health)
        return triggers

    @staticmethod
    def _phase_streaks(state: NexusState) -> Dict[str, int]:
        raw = state.metadata.get("phase_health_below_85_streak")
        if not isinstance(raw, dict):
            raw = {}
        normalized: Dict[str, int] = {}
        for key in ("P", "X", "D", "R", "A", "C"):
            value = raw.get(key, 0)
            try:
                normalized[key] = int(value)
            except (TypeError, ValueError):
                normalized[key] = 0
        state.metadata["phase_health_below_85_streak"] = normalized
        return normalized

    @staticmethod
    def _record(state: NexusState, triggers: List[HealthTrigger], pipeline_health: float) -> None:
        state.metadata["health_trigger_policy"] = {
            "pipeline_health": round(float(pipeline_health), 2),
            "triggers": [
                {
                    "code": trigger.code,
                    "reason": trigger.reason,
                    "severity": trigger.severity,
                    "target_phase": trigger.target_phase,
                }
                for trigger in triggers
            ],
        }
