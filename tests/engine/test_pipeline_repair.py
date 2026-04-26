import pytest
from unittest.mock import MagicMock, patch
import json
from nexus.engine.pipeline_repair import PipelineRepairMixin, AuditEvalContext
from nexus.core.state_contracts import NexusState

class MockPipeline(PipelineRepairMixin):
    def __init__(self):
        self.engine = MagicMock()
        self.engine.project_root = "/tmp"
        self.engine.max_retries = 3
        self.engine.ReviewStatusNormalizer.normalize.return_value = ("APPROVED", True)

    def _register_phase_decision(self, ctx, phase, skill_id):
        return f"dec_{phase.lower()}_mock"

@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.task_id = "test-task"
    ctx.state = NexusState(task_id="test-task")
    ctx.state.metadata = {"phase_decisions": {}, "phase_skills": {}}
    ctx.pack = {"learned_skills": []}
    ctx.repairer = MagicMock()
    ctx.accumulator = MagicMock()
    ctx.dry_run = False
    return ctx

@pytest.fixture
def mock_tracer():
    tracer = MagicMock()
    tracer.phase_span.return_value.__enter__.return_value = MagicMock()
    return tracer

def test_execute_single_repair_success(mock_ctx, mock_tracer):
    pipeline = MockPipeline()
    mock_ctx.repairer.run.return_value = {"status": "APPROVED", "result_object": {"patch_generated": True}}
    
    with patch("nexus.engine.pipeline_repair.run_cli_pregate") as mock_pregate:
        mock_pregate.return_value = (True, [])
        mock_ctx.state.metadata["verification_commands"] = ["test"]
        
        res = pipeline._execute_single_repair(mock_ctx, mock_tracer, 1)
        
        assert res["status"] == "APPROVED"
        assert mock_ctx.repairer.run.called
        assert mock_ctx.state.metadata["last_review_status"] == "APPROVED"

@patch("nexus.engine.pipeline_repair.detect_inconclusive_success")
def test_evaluate_audit_result_phantom(mock_detect, mock_ctx, mock_tracer):
    mock_detect.return_value = "no_physical_proof"
    
    pipeline = MockPipeline()
    eval_ctx = AuditEvalContext(
        tracer=mock_tracer,
        repair_attempts=1,
        review_status_raw="APPROVED",
        result_object={"patch_generated": True},
        current_decision_id="dec_r_mock",
        current_skill_id="repairer"
    )
    
    res = pipeline._evaluate_audit_result(mock_ctx, eval_ctx)
    
    assert res["audit_success"] is False
    assert res["status"] == "REJECTED"
    assert res["phantom_reason"] == "no_physical_proof"
    assert mock_ctx.state.metadata["phantom_success_reason"] == "no_physical_proof"

def test_handle_escalation_triggers(mock_ctx):
    pipeline = MockPipeline()
    mock_ctx.state.metadata["rejection_history"] = ["rejected:FAIL", "rejected:FAIL"]
    
    with patch("nexus.engine.pipeline_repair.analyze_cycle") as mock_analyze:
        mock_analyze.return_value = {"root_cause": "scope_drift"}
        
        res = pipeline._handle_escalation(mock_ctx, 3, "FAIL", "")
        
        # _handle_escalation returns (break_auto, replan_ok) tuple
        assert isinstance(res, tuple)
        assert mock_ctx.state.metadata["escalation_triggered"] is True
        assert mock_ctx.state.metadata["escalation_root_cause"] == "scope_drift"

def test_repair_audit_loop_success(mock_ctx, mock_tracer):
    pipeline = MockPipeline()
    # Mock _execute_single_repair and _evaluate_audit_result to succeed on first try
    pipeline._execute_single_repair = MagicMock(return_value={
        "status": "APPROVED", "result": {}, "current_decision_id": "dec_r", "current_skill_id": "sk"
    })
    pipeline._evaluate_audit_result = MagicMock(return_value={"audit_success": True})
    
    success = pipeline._repair_audit_loop(mock_ctx, mock_tracer)
    
    assert success is True
    assert pipeline._execute_single_repair.call_count == 1


def test_build_hallucination_evidence_bundle_collects_paths_and_commands(tmp_path, mock_ctx):
    pipeline = MockPipeline()
    pipeline.engine.project_root = tmp_path
    mock_ctx.state.metadata["cli_pregate_results"] = [
        {"cmd": "uv run pytest -q tests/a.py", "exit_code": 0, "stdout_tail": "ok"},
        {"cmd": "uv run pytest -q tests/b.py", "exit_code": 1, "stdout_tail": "fail"},
    ]

    class MockRun:
        returncode = 0
        stdout = "nexus/engine/pipeline_repair.py\nnexus/core/state_contracts.py\n"

    with patch("nexus.engine.pipeline_repair.subprocess.run", return_value=MockRun()):
        bundle = pipeline._build_hallucination_evidence_bundle(mock_ctx)

    assert bundle["code_artifacts"] == [
        "nexus/engine/pipeline_repair.py",
        "nexus/core/state_contracts.py",
    ]
    assert len(bundle["test_artifacts"]) == 2
    assert bundle["command_artifacts"] == [
        "uv run pytest -q tests/a.py -> rc=0",
        "uv run pytest -q tests/b.py -> rc=1",
    ]


def test_write_hallucination_evidence_bundle_persists_expected_shape(tmp_path, mock_ctx):
    pipeline = MockPipeline()
    pipeline.engine.project_root = tmp_path
    mock_ctx.state.metadata["cli_pregate_results"] = [
        {"cmd": "uv run pytest -q tests/a.py", "exit_code": 0, "stdout_tail": "ok"},
    ]

    class MockRun:
        returncode = 0
        stdout = "nexus/engine/pipeline_repair.py\n"

    with patch("nexus.engine.pipeline_repair.subprocess.run", return_value=MockRun()):
        evidence_path = pipeline._write_hallucination_evidence_bundle(mock_ctx)

    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert "evidence_bundle" in payload
    assert payload["evidence_bundle"]["code_artifacts"] == ["nexus/engine/pipeline_repair.py"]
    assert payload["evidence_bundle"]["command_artifacts"] == ["uv run pytest -q tests/a.py -> rc=0"]
