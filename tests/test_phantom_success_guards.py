from pathlib import Path
from unittest.mock import MagicMock

from nexus.engine.pipeline import NexusPipeline
from nexus.services.reviewer import CodexLoopV2


def _build_reviewer_with_llm_payload(payload, apply_patch=True):
    mock_git = MagicMock()
    mock_git.project_root = "."
    mock_git.get_changes.return_value = (["test.py"], "diff")

    mock_llm = MagicMock()
    mock_llm.ask.return_value = (payload, "raw")

    mock_linter = MagicMock()
    mock_patcher = MagicMock()
    mock_patcher.apply.return_value = False

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
    )
    result = reviewer.run_review()
    assert result["status"] == "REJECTED"
    assert result["patch_apply_success"] is False
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
