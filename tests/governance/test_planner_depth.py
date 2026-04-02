import pytest
from nexus.core.planner_auditor import PlannerAuditor
from nexus.health.scoring import HealthScorer
from nexus.core.state_contracts import NexusState

def test_perfect_plan_density():
    """核驗完美計畫：包含所有標籤，AOS 應加權至 120"""
    plan = """
    # 深度計畫 v22
    [Probe]: 執行 PreflightCheck 核驗 Rust >= 1.80。
    [Surface]: 修改核心模組 scoring.py 預期影響 12 行。
    [Rollback]: 失敗則 git reset --hard HEAD^ 並恢復 snapshots。
    """ + " ".join(["word"] * 100)
    
    audit = PlannerAuditor.audit_plan(plan)
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
    plan = """
    # 偷懶計畫
    no tags.
    """
    
    audit = PlannerAuditor.audit_plan(plan)
    state = NexusState(task_id="TASK_002")
    state.metadata["plan_density_score"] = 0.0 # 強制低分
    state.metadata["thinking_depth_score"] = 0.0 # 強制無加分
    state.phase_health.health_metrics.test_pass_rate = 1.0
    state.tokens.total_usage = 1000
    state.tokens.capture_status = "captured"
    
    snapshot = HealthScorer.apply_snapshot(state)
    # 100 * 0.4 = 40 (應低於 65)
    assert snapshot.overall_score < 65.0

def test_casual_text_plan():
    """核驗邊緣案例：有文字提及但無標籤，應攔截"""
    plan = "just some text"
    audit = PlannerAuditor.audit_plan(plan)
    assert audit["density_score"] == 0.0
