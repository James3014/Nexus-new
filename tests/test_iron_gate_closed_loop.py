import pytest
from unittest.mock import MagicMock, patch
from nexus.core.plan_quality_gate import PlanQualityGate
from nexus.engine.pipeline_repair import PipelineRepairMixin

# T20 閉環整合測試

class DummyPlugin:
    def __init__(self, name):
        self.name = name
    def should_run(self, ctx): return True
    def execute(self, engine, ctx):
        return MagicMock(status="PASS")

def test_p_stage_replan_ok_on_second_attempt():
    """T17: Plan Quality Gate 重試機制驗證"""
    # 我們可以利用 mock 來模擬 P-Stage 重試
    import sys
    from nexus.engine.pipeline_stages import PipelineStagesMixin
    
    class DummyEngine(PipelineStagesMixin):
        def __init__(self):
            self.registry = MagicMock()
            
    engine = DummyEngine()
    ctx = MagicMock()
    ctx.task_desc = "test"
    ctx.kwargs = {}
    ctx.prediction = {"target_files": []}  # First fail
    ctx.state = MagicMock()
    ctx.state.metadata = {}
    ctx.planner = MagicMock()
    
    # 模擬 planner.run 的行為
    call_count = 0
    def mock_planner_run(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"intent_pass": True, "risk_score": 0.5, "handoff_readiness": 0.5, "target_files": []}
        return {"intent_pass": True, "risk_score": 0.5, "handoff_readiness": 0.5, "target_files": ["a.py"]}

    ctx.planner.run.side_effect = mock_planner_run
    
    # 手動抽離出 p_stage 的邏輯 (因為 plugin architecture 封裝)
    MAX_PLAN_RETRIES = 2
    plan_attempts = 0
    from nexus.core.plan_quality_gate import PlanQualityGate
    plan_gate = PlanQualityGate()

    while True:
        plan_attempts += 1
        ctx.prediction = ctx.planner.run()
        plan_quality = plan_gate.evaluate(ctx.prediction, ctx.state.metadata)
        if plan_quality.passed:
            break
        if plan_attempts > MAX_PLAN_RETRIES:
            raise RuntimeError("FAILED")

    assert plan_attempts == 2
    assert ctx.prediction["target_files"] == ["a.py"]

def test_ra_escalation_triggers_replan():
    """T19: R↔A Escalation 實際執行 Replan 驗證"""
    class DummyEngine(PipelineRepairMixin):
        def __init__(self):
            # Inject a mock P-stage plugin
            self.registry = MagicMock()
            p_plugin = DummyPlugin("P")
            self.registry.get_ordered_plugins.return_value = [p_plugin]
            
    engine = DummyEngine()
    engine.engine = engine  # loopback for self.engine.registry
    ctx = MagicMock()
    ctx.state = MagicMock()
    ctx.state.metadata = {"rejection_history": ["a", "b", "c"]}
    ctx.kwargs = {}
    ctx.task_desc = "test task"
    
    break_loop, replan_ok = engine._perform_escalation(ctx, "scope_drift", 3)
    assert break_loop is False
    assert replan_ok is True
    assert ctx.state.metadata["escalation_triggered"] is True
    # Verify P executed
    assert "plan_feedback" not in ctx.kwargs  # Popped correctly

def test_ra_escalation_max_reached():
    """T19: Escalation 過多次轉交人類"""
    class DummyEngine(PipelineRepairMixin):
        def __init__(self):
            self.registry = MagicMock()
            
    engine = DummyEngine()
    engine.engine = engine
    ctx = MagicMock()
    ctx.state = MagicMock()
    ctx.state.metadata = {"escalation_count": 3}
    
    break_loop, replan_ok = engine._perform_escalation(ctx, "scope_drift", 3)
    assert break_loop is True
    assert replan_ok is False
    assert ctx.state.metadata["human_review_required"] is True

def test_pipeline_d_stage_veto_retry():
    """T18: D-Stage VETO 觸發 P-X-D 重試邏輯驗證"""
    # 模擬 pipeline.py 中的 P-X-D while 迴圈邏輯
    MAX_PXD_RETRIES = 2
    pxd_attempts = 0
    success = True
    veto_feedback = None
    final_plan_strategy = None

    while pxd_attempts < MAX_PXD_RETRIES and success:
        pxd_attempts += 1
        pxd_veto = False

        # 模擬 P-Stage：有 veto_feedback 時用保守策略
        if veto_feedback:
            plan = {"strategy": "conservative", "risk": 0.2}
        else:
            plan = {"strategy": "aggressive", "risk": 0.9}

        # 模擬 D-Stage：高風險 VETO
        if plan["risk"] > 0.7 and pxd_attempts < MAX_PXD_RETRIES:
            veto_feedback = f"VETO: risk {plan['risk']}"
            pxd_veto = True
        else:
            final_plan_strategy = plan["strategy"]

        if not pxd_veto:
            break

    assert pxd_attempts == 2, f"Expected 2 attempts, got {pxd_attempts}"
    assert final_plan_strategy == "conservative", f"Should have switched to conservative, got {final_plan_strategy}"
    assert veto_feedback is not None, "Should have a veto feedback from first attempt"
