from pathlib import Path
from unittest.mock import ANY, MagicMock, call

from nexus.engine.pipeline import NexusPipeline
from nexus.services.reviewer import CodexLoopV2


def _build_reviewer_with_llm_payload(payload, apply_patch=True, patch_apply_result=False):
    mock_git = MagicMock()
    mock_git.project_root = "."
    mock_git.get_changes.return_value = (["test.py"], "diff")

    mock_llm = MagicMock()
    mock_llm.ask.return_value = (payload, "raw")

    mock_linter = MagicMock()
    mock_patcher = MagicMock()
    mock_patcher.apply.return_value = patch_apply_result

    reviewer = CodexLoopV2(
        project_root=".",
        git=mock_git,
        llm=mock_llm,
        linter=mock_linter,
        patcher=mock_patcher,
        apply_patch=apply_patch,
    )
    return reviewer, mock_patcher


def test_reviewer_rejects_pass_without_patch_or_no_change_reason():
    reviewer, _ = _build_reviewer_with_llm_payload(
        {"status": "PASS", "summary": "looks good", "violations": []},
        apply_patch=False,
    )
    result = reviewer.run_review()
    assert result["status"] == "REJECTED"
    assert "no_change_reason" in result["summary"]


def test_reviewer_rejects_when_patch_apply_fails():
    reviewer, patcher = _build_reviewer_with_llm_payload(
        {
            "status": "PASS",
            "summary": "fixed",
            "patch_generated": True,
            "violations": [
                {
                    "file": "test.py",
                    "patch": "--- a/test.py\n+++ b/test.py\n@@\n-old\n+new\n",
                }
            ],
        },
        apply_patch=True,
        patch_apply_result=False,
    )
    result = reviewer.run_review()
    assert result["status"] == "REJECTED"
    assert result["patch_apply_success"] is False
    patcher.apply.assert_called_once()


def test_reviewer_rejects_when_patch_apply_succeeds_but_missing_proof():
    reviewer, patcher = _build_reviewer_with_llm_payload(
        {
            "status": "PASS",
            "summary": "fixed",
            "patch_generated": True,
            "violations": [
                {
                    "file": "test.py",
                    "patch": "--- a/test.py\n+++ b/test.py\n@@\n-old\n+new\n",
                }
            ],
        },
        apply_patch=True,
        patch_apply_result=True,
    )
    reviewer._collect_physical_proof = MagicMock(return_value=("", ""))
    result = reviewer.run_review()
    assert result["status"] == "REJECTED"
    assert result["summary"].endswith("missing_physical_proof")
    patcher.apply.assert_called_once()


def test_pipeline_blocks_audit_pass_when_patch_apply_failed():
    engine = MagicMock()
    engine.hub.make_pre_routing_decision.return_value = {}
    engine.hub.assemble_diag_pack.return_value = {"task": "t"}
    engine.hub.assemble_feature_pack.return_value = {"task": "t"}
    engine.accumulator.record.return_value = None
    engine.health_evaluator.evaluate.return_value = 50.0
    engine.research_policy.should_research.return_value = False
    engine.max_retries = 1
    engine._add_step_to_history.return_value = None
    engine.ReviewStatusNormalizer.normalize.return_value = ("APPROVED", True)
    engine.commander.crystallize.return_value = None
    engine.state_io.save_global_state.return_value = None
    engine.run_dir = Path(".")

    planner = MagicMock()
    planner.run.return_value = {"ok": True}
    researcher = MagicMock()
    repairer = MagicMock()
    repairer.run.return_value = {
        "status": "APPROVED",
        "result_object": {
            "patch_generated": True,
            "patch_apply_success": False,
            "no_change_reason": "",
        },
    }
    engine.phases = {"P": planner, "X": researcher, "R": repairer}

    pipeline = NexusPipeline(engine)
    ok = pipeline.run("fix phantom success", task_type="bug")
    assert ok is False


def test_reviewer_bypass_carries_no_change_reason():
    mock_git = MagicMock()
    mock_git.project_root = "."
    mock_git.get_changes.return_value = (["test.py"], "diff")

    reviewer = CodexLoopV2(
        project_root=".",
        git=mock_git,
        llm=MagicMock(),
        linter=MagicMock(),
        patcher=MagicMock(),
        apply_patch=False,
        audit_level="bypass",
    )
    result = reviewer.run_review()
    assert result["status"] == "APPROVED"
    assert result["patch_generated"] is False
    assert result["no_change_reason"] == "audit_level=bypass"


def test_pipeline_forces_x_phase_when_benchmark_force_research_enabled():
    engine = MagicMock()
    engine.hub.make_pre_routing_decision.return_value = {}
    engine.hub.assemble_diag_pack.return_value = {"task": "t"}
    engine.hub.assemble_feature_pack.return_value = {"task": "t"}
    engine.accumulator.record.return_value = None
    engine.health_evaluator.evaluate.return_value = 90.0
    engine.research_policy.should_research.return_value = False
    engine.max_retries = 1
    engine._add_step_to_history.return_value = None
    engine.ReviewStatusNormalizer.normalize.return_value = ("APPROVED", True)
    engine.commander.next_step.return_value = None
    engine.state_io.save_global_state.return_value = None
    engine.policy_manager.apply_policy_to_state.return_value = None

    planner = MagicMock()
    planner.run.return_value = {"ok": True}
    researcher = MagicMock()
    researcher.run.return_value = {"findings": ["forced"]}
    repairer = MagicMock()
    repairer.run.return_value = {
        "status": "APPROVED",
        "result_object": {
            "patch_generated": True,
            "patch_apply_success": True,
            "proof_type": "checksum",
            "proof_value": "abc123",
        },
    }
    engine.phases = {"P": planner, "X": researcher, "R": repairer}

    pipeline = NexusPipeline(engine)
    ok = pipeline.run(
        "force research",
        task_type="bug",
        context={"benchmark_force_research": True},
    )
    assert ok is True
    researcher.run.assert_called_once()


def test_pipeline_records_c_before_commander_completion():
    engine = MagicMock()
    engine.hub.make_pre_routing_decision.return_value = {}
    engine.hub.assemble_diag_pack.return_value = {"task": "t"}
    engine.accumulator.record.return_value = None
    engine.health_evaluator.evaluate.return_value = 90.0
    engine.research_policy.should_research.return_value = False
    engine.max_retries = 1
    engine.ReviewStatusNormalizer.normalize.return_value = ("APPROVED", True)
    engine.state_io.save_global_state.return_value = None
    engine.policy_manager.apply_policy_to_state.return_value = None
    engine.commander.next_step.return_value = None

    phase_calls = []

    def _record_step(state, phase, metadata=None):
        phase_calls.append(phase)
        return None

    engine._add_step_to_history.side_effect = _record_step

    planner = MagicMock()
    planner.run.return_value = {"ok": True}
    researcher = MagicMock()
    repairer = MagicMock()
    repairer.run.return_value = {
        "status": "APPROVED",
        "result_object": {
            "patch_generated": True,
            "patch_apply_success": True,
            "proof_type": "checksum",
            "proof_value": "abc123",
        },
    }
    engine.phases = {"P": planner, "X": researcher, "R": repairer}

    pipeline = NexusPipeline(engine)
    ok = pipeline.run("validate c ordering", task_type="bug")

    assert ok is True
    assert phase_calls[-1] == "C"
    engine.commander.next_step.assert_has_calls(
        [call(status="started"), call(status="completed", state=ANY)]
    )
