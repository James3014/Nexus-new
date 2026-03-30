import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class LearningGateConfig:
    """🧠 學習提拔門檻設定 (0-100 量尺)"""
    pattern_reuse_min: float = 30.0
    next_run_hit_min: float = 20.0

@dataclass
class LearningGateResult:
    passed: bool
    pattern_reuse: float
    next_run_hit: float
    lesson_quality: float  # 第一版僅供觀測
    failure_reasons: list[str]

def evaluate_learning_gate(run_dir: Path, project_root: Path, config: LearningGateConfig = None) -> LearningGateResult:
    """
    評估是否通過學習門檻 (Trust Promotion Gate)。
    讀取目前 run_dir 中的 outcome event，或是從全域 telemetry 過濾出最近一筆。
    """
    if config is None:
        config = LearningGateConfig()

    event_data = None
    # 嘗試從執行目錄讀取 artifact
    run_outcome_file = run_dir / "outcome_event.json"
    if run_outcome_file.exists():
        try:
            event_data = json.loads(run_outcome_file.read_text())
        except Exception:
            pass

    # 如果沒有，去全域找最後一筆 (作為 fallback)
    if not event_data:
        global_outcome_file = project_root / ".nexus" / "telemetry" / "skill_outcome_events.jsonl"
        if global_outcome_file.exists():
            try:
                # 簡單取最後一行
                lines = global_outcome_file.read_text().splitlines()
                if lines:
                    event_data = json.loads(lines[-1])
            except Exception:
                pass

    if not event_data:
        logger.warning("No outcome event found for learning gate evaluation. Passing by default for bootstrap.")
        return LearningGateResult(True, 0.0, 0.0, 0.0, [])
        
    # 提取量尺並確保是 float (0-100)
    def _extract_metric(key: str) -> float:
        val = event_data.get(key)
        if val is None:
            # Maybe inside metadata
            val = event_data.get("metadata", {}).get(key, 0.0)
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    pattern_reuse = _extract_metric("pattern_reuse")
    next_run_hit = _extract_metric("next_run_hit")
    lesson_quality = _extract_metric("lesson_quality") # 僅觀測不硬擋

    passed = True
    reasons = []

    if pattern_reuse < config.pattern_reuse_min:
        passed = False
        reasons.append(f"pattern_reuse ({pattern_reuse:.1f}) < {config.pattern_reuse_min:.1f}")
        
    if next_run_hit < config.next_run_hit_min:
        passed = False
        reasons.append(f"next_run_hit ({next_run_hit:.1f}) < {config.next_run_hit_min:.1f}")

    if not passed:
        logger.warning(f"🛑 Learning Gate Failed: {', '.join(reasons)}")
    else:
        logger.info(f"✨ Learning Gate Passed: PR={pattern_reuse:.1f}, NRH={next_run_hit:.1f}")

    return LearningGateResult(
        passed=passed,
        pattern_reuse=pattern_reuse,
        next_run_hit=next_run_hit,
        lesson_quality=lesson_quality,
        failure_reasons=reasons
    )
