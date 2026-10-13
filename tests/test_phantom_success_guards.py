from unittest.mock import MagicMock, patch

from nexus.engine.phase_plugin import PhaseResult
from nexus.engine.pipeline import NexusPipeline
from nexus.engine.pipeline_outcome import PipelineTerminalState
from nexus.services.reviewer import CodexLoopV2


class _FakeExecutor:
    """Composition phase executor injected through engine.phase_executors."""

    def __init__(self, name, mutations, *, events=None, side_effect=None):
        self.name = name
        self.mutations = mutations
        self.events = events
        self.side_effect = side_effect
        self.calls = 0

    def should_run(self, _ctx):
        return True

    def execute(self, _pipeline, ctx):
        self.calls += 1
        if self.events is not None:
            self.events.append(("phase", self.name))
        if self.side_effect is not None:
            self.side_effect(ctx)
        return PhaseResult(status="success", mutations=dict(self.mutations), events=[])


def _write_terminal_record(ctx):
    metadata = ctx.state.metadata
    if metadata.get("human_review_required"):
        terminal = "HUMAN_REVIEW"
    else:
        terminal = "SUCCESS" if metadata.get("pipeline_success") else "FAILED"
    metadata["pipeline_terminal_state"] = terminal
    metadata["pipeline_outcome"] = {
        "terminal_state": PipelineTerminalState[terminal],
        "exit_code": PipelineTerminalState[terminal].value,
    }
    metadata["nexus_outcome_v2"] = {
        "terminal_state": terminal,
        "exit_code": PipelineTerminalState[terminal].value,
        "trust_level": "production",
    }


def _write_terminal_record_then_raise(ctx):
    _write_terminal_record(ctx)
    raise RuntimeError("crystallize index write failed")


def _composition_executors(*, events=None, c_writes_terminal_record=True):
    return {
        "P": _FakeExecutor("P", {"plan": "ok"}, events=events),
        "X": _FakeExecutor("X", {"findings": ["forced"]}, events=events),
        "D": _FakeExecutor("D", {"diagnosis": "ok"}, events=events),
        "R": _FakeExecutor(
            "R",
            {
                "status": "APPROVED",
                "result_object": {
                    "patch_generated": True,
                    "patch_apply_success": True,
                    "proof_type": "checksum",
                    "proof_value": "abc123",
                },
            },
            events=events,
        ),
        "A": _FakeExecutor("A", {"status": "APPROVED"}, events=events),
        "C": _FakeExecutor(
            "C",
            {"status": "COMPLETED"},
            events=events,
            side_effect=_write_terminal_record if c_writes_terminal_record else None,
        ),
    }


def _composition_engine(tmp_path, executors):
    engine = MagicMock()
    engine.project_root = tmp_path
    engine.run_dir = tmp_path
    engine.max_retries = 1
    engine.health_evaluator.evaluate.return_value = 90.0
    engine.phase_executors = executors
    return engine


def _capture_final_metadata(pipeline):
    seen = {}
    finalize = pipeline._finalize_and_report

    def _finalize(ctx, success, tracer):
        result = finalize(ctx, success, tracer)
        seen.update(ctx.state.metadata)
        return result

    pipeline._finalize_and_report = _finalize
    return seen


def _receipt_phases(metadata):
    return [receipt["phase"] for receipt in metadata.get("phase_receipts", [])]


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
    # Issue #436: a phantom-success guard trip is a repairable, non-accepting
    # block; terminal REJECTED is reserved for an explicit reviewer disposition.
    assert result["status"] == "RECOVERABLE_BLOCK"
    assert result["status"] != "APPROVED"
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
    # Issue #436: a phantom-success guard trip is a repairable, non-accepting
    # block; terminal REJECTED is reserved for an explicit reviewer disposition.
    assert result["status"] == "RECOVERABLE_BLOCK"
    assert result["status"] != "APPROVED"
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
    # Issue #436: a phantom-success guard trip is a repairable, non-accepting
    # block; terminal REJECTED is reserved for an explicit reviewer disposition.
    assert result["status"] == "RECOVERABLE_BLOCK"
    assert result["status"] != "APPROVED"
    assert result["summary"].endswith("missing_physical_proof")
    patcher.apply.assert_called_once()


@patch("nexus.learning.knowledge_index.KnowledgeIndex")
@patch("nexus.engine.pipeline_repair._auto_detect_verify_commands", return_value=[])
def test_pipeline_blocks_audit_pass_when_patch_apply_failed(mock_auto_detect, mock_ki, tmp_path):
    # R claims APPROVED with a generated but unapplied patch; the composed A
    # executor would pass. The pipeline itself must withhold success and say why.
    executors = _composition_executors()
    executors["R"] = _FakeExecutor(
        "R",
        {
            "status": "APPROVED",
            "result_object": {
                "patch_generated": True,
                "patch_apply_success": False,
                "no_change_reason": "",
            },
        },
    )
    engine = _composition_engine(tmp_path, executors)
    pipeline = NexusPipeline(engine)
    seen = _capture_final_metadata(pipeline)

    ok = pipeline.run("fix phantom success", task_type="bug")

    assert ok is False
    assert executors["A"].calls == 1
    assert seen["composition_audit_phase_rejection"] == "patch_apply_failed"
    assert seen["phantom_success_reason"] == "patch_apply_failed"
    assert seen["pipeline_terminal_state"] == "FAILED"
    audit_receipts = [r for r in seen["phase_receipts"] if r["phase"] == "A"]
    assert [r["block_class"] for r in audit_receipts] == ["RECOVERABLE_BLOCK"]


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


@patch("nexus.learning.knowledge_index.KnowledgeIndex")
def test_pipeline_forces_x_phase_when_benchmark_force_research_enabled(mock_ki, tmp_path):
    def _run(context):
        executors = _composition_executors()
        pipeline = NexusPipeline(_composition_engine(tmp_path, executors))
        seen = _capture_final_metadata(pipeline)
        ok = pipeline.run("force research", task_type="bug", context=context)
        return ok, executors, seen

    # Control: no research signal, so X stays off.
    ok, executors, seen = _run({})
    assert ok is True
    assert executors["X"].calls == 0
    assert "X" not in _receipt_phases(seen)

    # Benchmark force-research alone must make the X executor actually run.
    ok, executors, seen = _run({"benchmark_force_research": True})
    assert ok is True
    assert executors["X"].calls == 1
    assert _receipt_phases(seen) == ["P", "D", "X", "R", "A", "C"]


@patch("nexus.learning.knowledge_index.KnowledgeIndex")
def test_pipeline_records_c_before_commander_completion(mock_ki, tmp_path):
    events = []

    def _run(executors):
        engine = _composition_engine(tmp_path, executors)
        engine.commander.next_step.side_effect = lambda **kwargs: events.append((
            "commander",
            kwargs.get("status"),
        ))
        pipeline = NexusPipeline(engine)
        seen = _capture_final_metadata(pipeline)
        ok = pipeline.run("validate c ordering", task_type="bug")
        return ok, seen

    # With a C executor that writes the terminal record, success is claimed
    # only after C is recorded, and no completion signal precedes C.
    executors = _composition_executors(events=events)
    ok, seen = _run(executors)
    assert ok is True
    assert executors["C"].calls == 1
    assert _receipt_phases(seen)[-1] == "C"
    assert seen["composition_crystallize_side_effects_verified"] is True
    assert seen["pipeline_terminal_state"] == "SUCCESS"
    assert events[0] == ("commander", "started")
    c_index = events.index(("phase", "C"))
    assert all(event != ("commander", "completed") for event in events[:c_index])

    # Without a verified C record the pipeline must not claim success.
    executors = _composition_executors()
    del executors["C"]
    ok, seen = _run(executors)
    assert ok is False
    assert "C" not in _receipt_phases(seen)
    assert seen["composition_crystallize_failure_reason"] == "missing_crystallize_executor"
    assert seen["pipeline_terminal_state"] == "FAILED"

    executors = _composition_executors(c_writes_terminal_record=False)
    ok, seen = _run(executors)
    assert ok is False
    assert seen["composition_crystallize_failure_reason"] == "missing_terminal_outcome_side_effects"
    assert seen["pipeline_terminal_state"] == "FAILED"


@patch("nexus.learning.knowledge_index.KnowledgeIndex")
def test_pipeline_blocks_audit_pass_when_repair_failed(mock_ki, tmp_path):
    # R reports FAILED; a permissive composed A must not turn it into success.
    executors = _composition_executors()
    executors["R"] = _FakeExecutor("R", {"status": "FAILED"})
    pipeline = NexusPipeline(_composition_engine(tmp_path, executors))
    seen = _capture_final_metadata(pipeline)

    ok = pipeline.run("repair failed", task_type="bug")

    assert ok is False
    assert executors["A"].calls == 1
    assert seen["composition_audit_phase_rejection"] == "composition_repair_recoverable_block"
    assert seen["pipeline_terminal_state"] == "FAILED"


@patch("nexus.learning.knowledge_index.KnowledgeIndex")
def test_pipeline_withholds_success_when_crystallize_raises(mock_ki, tmp_path):
    # C writes a SUCCESS record and then raises: the run must end FAILED and
    # no persisted outcome may still claim SUCCESS.
    executors = _composition_executors()
    executors["C"].side_effect = _write_terminal_record_then_raise
    pipeline = NexusPipeline(_composition_engine(tmp_path, executors))
    seen = _capture_final_metadata(pipeline)

    ok = pipeline.run("crystallize raises", task_type="bug")

    assert ok is False
    assert executors["C"].calls == 1
    assert seen.get("composition_crystallize_side_effects_verified") is not True
    assert seen["pipeline_terminal_state"] == "FAILED"
    assert seen["pipeline_outcome"]["terminal_state"] == PipelineTerminalState.FAILED
    assert seen["pipeline_outcome"]["exit_code"] == PipelineTerminalState.FAILED.value
    assert seen["nexus_outcome_v2"]["terminal_state"] == "FAILED"
    assert seen["nexus_outcome_v2"]["exit_code"] == PipelineTerminalState.FAILED.value
    assert seen["nexus_outcome_v2"]["trust_level"] == "untrusted"


@patch("nexus.learning.knowledge_index.KnowledgeIndex")
def test_pipeline_preserves_human_review_when_crystallize_raises(mock_ki, tmp_path):
    # C writes HUMAN_REVIEW and then raises. Whether or not R/A succeeded, the
    # HUMAN_REVIEW terminal state and its handoff bundle must survive.
    for repair_status in ("APPROVED", "FAILED"):
        executors = _composition_executors()
        executors["R"] = _FakeExecutor("R", {"status": repair_status})
        executors["C"].side_effect = _write_terminal_record_then_raise
        pipeline = NexusPipeline(_composition_engine(tmp_path, executors))
        seen = _capture_final_metadata(pipeline)

        with patch("nexus.engine.pipeline.HandoffBundleWriter") as writer:
            ok = pipeline.run(
                "human review",
                task_type="bug",
                context={"human_review_required": True},
            )

        assert ok is False, repair_status
        assert seen["pipeline_terminal_state"] == "HUMAN_REVIEW", repair_status
        assert seen["pipeline_outcome"]["terminal_state"] == PipelineTerminalState.HUMAN_REVIEW
        assert seen["nexus_outcome_v2"]["terminal_state"] == "HUMAN_REVIEW"
        writer.return_value.create.assert_called_once()
