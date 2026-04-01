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
    
    補充內容：這是一個非常詳盡的計畫，確保所有物理通路導通。
    """ + " ".join(["word"] * 100) # 補齊長度
    
    audit = PlannerAuditor.audit_plan(plan)
    assert audit["density_score"] == 1.0
    assert audit["status"] == "HEALTHY"
    
    state = NexusState()
    state.metadata["plan_density_score"] = audit["density_score"]
    state.metadata["thinking_depth_score"] = audit["thinking_depth_score"]
    state.health_metrics.outcome_quality = 1.0
    
    snapshot = HealthScorer.build_snapshot(state)
    assert snapshot.overall_score >= 100.0

def test_insufficient_plan_penalty():
    """核驗計畫密度缺失處：缺失 Rollback，AOS 應低於 60"""
    plan = """
    # 偷懶計畫
    [Probe]: 無。
    [Surface]: 修改一些代碼。
    """
    
    audit = PlannerAuditor.audit_plan(plan)
    assert audit["density_score"] < 0.6
    assert audit["status"] == "INSUFFICIENT_THOUGHT"
    
    state = NexusState()
    state.metadata["plan_density_score"] = audit["density_score"]
    state.health_metrics.outcome_quality = 1.0 # 雖然結果本身沒問題
    
    snapshot = HealthScorer.build_snapshot(state)
    # 100 * 0.4 = 40 (應低於 60)
    assert snapshot.overall_score < 60.0

def test_casual_text_plan():
    """核驗邊緣案例：有文字提及但無標籤，應攔截"""
    plan = """
    我打算修改一下 Surface 然後跑一下 Probe，最後如果不行的話就 Rollback。
    """
    audit = PlannerAuditor.audit_plan(plan)
    assert audit["density_score"] == 0.0
    assert audit["status"] == "INSUFFICIENT_THOUGHT"
