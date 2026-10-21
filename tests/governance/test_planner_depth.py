# nexus.core.planner_auditor was archived 2026-10-13 (#1906) and deleted 2026-10-21 (#2584
# Phase-2 batch B, ARCHIVED_2026-10-21_phase2_batch_B.md). The two HealthScorer cases cover
# live code (the plan-density weighting in HealthScorer.apply_snapshot) and are unchanged
# apart from the dropped auditor call and its plan text; the auditor-only case keeps its id
# and asserts the module is gone.
import importlib.util

from nexus.core.state_contracts import NexusState
from nexus.health.scoring import HealthScorer


def test_perfect_plan_density():
    """核驗完美計畫：包含所有標籤，AOS 應加權至 120"""
    state = NexusState(task_id="TASK_001")
    state.metadata["plan_density_score"] = 1.0
    state.metadata["thinking_depth_score"] = 1.0
    state.phase_health.health_metrics.test_pass_rate = 1.0
    state.tokens.total_usage = 1000
    state.tokens.capture_status = "captured"

    snapshot = HealthScorer.apply_snapshot(state)
    assert snapshot.overall_score >= 89.9


def test_insufficient_plan_penalty():
    """核驗計畫密度缺失處：缺失 Rollback，AOS 應低於 65"""
    state = NexusState(task_id="TASK_002")
    state.metadata["plan_density_score"] = 0.0  # 強制低分
    state.metadata["thinking_depth_score"] = 0.0  # 強制無加分
    state.phase_health.health_metrics.test_pass_rate = 1.0
    state.tokens.total_usage = 1000
    state.tokens.capture_status = "captured"

    snapshot = HealthScorer.apply_snapshot(state)
    # 100 * 0.4 = 40 (應低於 65)
    assert snapshot.overall_score < 65.0


def test_casual_text_plan():
    """核驗邊緣案例：有文字提及但無標籤，應攔截 (auditor retired, #2584)"""
    assert importlib.util.find_spec("nexus.core.planner_auditor") is None
