from pathlib import Path
import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class LearningGateConfig:
    """🧠 學習提拔門檻設定 (v24.0 Bayesian Hardened)"""
    pattern_reuse_min: float = 30.0
    next_run_hit_min: float = 20.0
    lesson_quality_min: float = 70.0 # 🧪 [v24.0] 啟用熵值感知硬擋
    bayesian_aggression: float = 0.5 # 🧪 [v24.0] 支援動態調整

@dataclass
class LearningGateResult:
    passed: bool
    pattern_reuse: float
    next_run_hit: float
    lesson_quality: float
    failure_reasons: list[str]

def evaluate_learning_gate(run_dir: Path, project_root: Path, config: LearningGateConfig = None) -> LearningGateResult:
    """
    評估是否通過學習門檻 (Trust Promotion Gate v24.0).
    """
    if config is None:
        config = LearningGateConfig()

    # 🧪 [v24.0 Evolution] Dynamic threshold scaling
    # High aggression means we are exploring -> lower the reuse barrier slightly to encourage new patterns
    actual_reuse_min = config.pattern_reuse_min * (1.0 - (config.bayesian_aggression * 0.3))

    event_data = None
    run_outcome_file = run_dir / "outcome_event.json"
    if run_outcome_file.exists():
        try:
            event_data = json.loads(run_outcome_file.read_text())
        except Exception:
            pass

    if not event_data:
        global_outcome_file = project_root / ".nexus" / "telemetry" / "skill_outcome_events.jsonl"
        if global_outcome_file.exists():
            try:
                lines = global_outcome_file.read_text().splitlines()
                if lines:
                    event_data = json.loads(lines[-1])
            except Exception:
                pass

    if not event_data:
        logger.warning("No outcome event found for learning gate evaluation. Passing by default for bootstrap.")
        return LearningGateResult(True, 0.0, 0.0, 0.0, [])
        
    def _extract_metric(key: str) -> float:
        val = event_data.get(key)
        if val is None:
            val = event_data.get("metadata", {}).get(key, 0.0)
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    pattern_reuse = _extract_metric("pattern_reuse")
    next_run_hit = _extract_metric("next_run_hit")
    lesson_quality = _extract_metric("lesson_quality") 

    passed = True
    reasons = []

    # 🧪 [v24.0] Judicial Explanations for Learning Rejections
    if pattern_reuse < actual_reuse_min:
        passed = False
        reasons.append(f"LEARNING_VIOLATION[REUSE]: {pattern_reuse:.1f} < adaptive min {actual_reuse_min:.1f}")
        
    if next_run_hit < config.next_run_hit_min:
        passed = False
        reasons.append(f"LEARNING_VIOLATION[HIT_RATE]: {next_run_hit:.1f} < absolute min {config.next_run_hit_min:.1f}")

    if lesson_quality < config.lesson_quality_min:
        passed = False
        reasons.append(f"LEARNING_VIOLATION[ENTROPY_HIGH]: lesson_quality {lesson_quality:.1f} < {config.lesson_quality_min:.1f}. Too chaotic to internalize.")

    if not passed:
        logger.warning(f"🛑 Learning Gate Failed: {', '.join(reasons)}")
    else:
        logger.info(f"✨ Learning Gate Passed: PR={pattern_reuse:.1f}, NRH={next_run_hit:.1f}, LQ={lesson_quality:.1f}")

    return LearningGateResult(
        passed=passed,
        pattern_reuse=pattern_reuse,
        next_run_hit=next_run_hit,
        lesson_quality=lesson_quality,
        failure_reasons=reasons
    )
