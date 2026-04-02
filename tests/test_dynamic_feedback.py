from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

from nexus.core.state_contracts import NexusState
from nexus.engine.pipeline import NexusPipeline
from nexus.engine.phases.repair import RepairPhaseHandler

class MockEngine:
    def __init__(self):
        self.max_retries = 3
        self.run_dir = Path("/tmp/mock_run")
        self.project_root = Path("/tmp/mock_root")
        
        self.hub = MagicMock()
        self.accumulator = MagicMock()
        self.policy_manager = MagicMock()
        self.health_evaluator = MagicMock()
        self.research_policy = MagicMock()
        self.ReviewStatusNormalizer = MagicMock()
        self.state_io = MagicMock()
        self.commander = MagicMock()

        self.phases = {
            "P": MagicMock(),
            "X": MagicMock(),
            "R": MagicMock()
        }
        
    def _add_step_to_history(self, *args, **kwargs):
        pass


def test_pipeline_injects_audit_failure_to_repairer():
    engine = MockEngine()
    pipeline = NexusPipeline(engine)
    
    # 模擬 第一次 R 的結果為通過但在 Gate 攔截 (沒有 patch_generated 且沒 no_change_reason)
    mock_repairer = engine.phases["R"]
    
    # 第一輪跑出爛結果，第二輪跑出好結果
    mock_repairer.run.side_effect = [
        {"status": "APPROVED", "result_object": {"patch_generated": False, "no_change_reason": ""}},
        {"status": "APPROVED", "result_object": {"patch_generated": False, "no_change_reason": "fixed"}}
    ]
    
    engine.ReviewStatusNormalizer.normalize.return_value = ("REJECTED", True)  # (status, audit_success) 配合第一輪的邏輯
    
    # Override the behavior of normalizer based on inputs during the loop manually if needed, 
    # but let's just assert that in the second call to `repairer.run()`, the 'pack' dictionary contains the feedback!
    
    state = NexusState(task_id="test-123")
    pack = {"original_data": 123}
    
def test_pipeline_injects_audit_failure_to_repairer():
    engine = MockEngine()
    pipeline = NexusPipeline(engine)
    
    # 模擬 第一次 R 的結果為通過但在 Gate 攔截 (沒有 patch_generated 且沒 no_change_reason)
    mock_repairer = engine.phases["R"]
    
    # 第一輪跑出爛結果，第二輪跑出好結果
    mock_repairer.run.side_effect = [
        {"status": "APPROVED", "result_object": {"patch_generated": False, "no_change_reason": ""}},
        {"status": "APPROVED", "result_object": {"patch_generated": False, "no_change_reason": "fixed"}}
    ]
    
    # Mock normalizer to always return (status, True) because our pipeline checks `if audit_success:` 
    # to evaluate the patch details in the gate.
    def mock_normalize(raw_status):
        return (raw_status, raw_status == "APPROVED")
    engine.ReviewStatusNormalizer.normalize.side_effect = mock_normalize
    
    state = NexusState(task_id="test-123")
    pack = {"original_data": 123}
    
    # Fake a planner/researcher/hub result to bypass P/X/D phases smoothly in pipeline.run
    engine.hub.make_pre_routing_decision.return_value = {}
    engine.hub.assemble_diag_pack.return_value = pack
    engine.research_policy.should_research.return_value = False
    engine.phases["P"].run.return_value = {}
    engine.health_evaluator.evaluate.return_value = 95.0
    
    # Run the pipeline!
    # Because of the gate logic, the first APPROVED lacks a no_change_reason, so it flips to REJECTED 
    # and populates state.metadata["last_audit_failure"]. Then attempt 2 happens.
    result = pipeline.run("Test task", task_type="bug", context={})
    
    assert result is True, "Pipeline should succeed on the second valid attempt"
    
    # Verify mock_repairer was called twice
    assert mock_repairer.run.call_count == 2
    
    # Verify that the SECOUND call to repairer.run contained the feedback loop injection in 'pack'
    second_call_pack = mock_repairer.run.call_args_list[1][0][1] # (state, pack) -> pack is index 1
    
    assert "audit_feedback" in second_call_pack, "pack must contain audit_feedback"
    assert "missing_no_change_reason" in second_call_pack["audit_feedback"]
    
    print("✅ test_pipeline_injects_audit_failure_to_repairer PASSED")
