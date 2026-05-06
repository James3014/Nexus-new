from __future__ import annotations

from types import SimpleNamespace

from nexus.engine.phase_executors import HandlerPhaseExecutor, build_crystallize_executor, build_diagnose_executor
from nexus.engine.phase_plugin import PhaseResult


class FakeHandler:
    name = "P"
    priority = 10

    def should_run(self, ctx):
        return not ctx.kwargs.get("skip")

    def execute(self, pipeline, ctx):
        return PhaseResult(status="success", mutations={"planned": True}, events=[])


class LegacyFailHandler:
    name = "A"
    priority = 40

    def run(self, _state, _pack):
        return {"status": "FAILED", "fail": True, "reason": "hallucination_gate_rejected"}


def test_handler_phase_executor_adapts_legacy_handler_shape():
    executor = HandlerPhaseExecutor(FakeHandler())
    ctx = SimpleNamespace(kwargs={})

    assert executor.name == "P"
    assert executor.priority == 10
    assert executor.should_run(ctx) is True
    assert executor.execute(None, ctx).mutations == {"planned": True}


def test_handler_phase_executor_honors_should_run():
    executor = HandlerPhaseExecutor(FakeHandler())
    ctx = SimpleNamespace(kwargs={"skip": True})

    assert executor.should_run(ctx) is False


def test_research_executor_records_skip_reason_when_should_run_is_false():
    class SkipResearchHandler:
        name = "X"
        priority = 20

        def should_run(self, _ctx):
            return False

    executor = HandlerPhaseExecutor(SkipResearchHandler())
    ctx = SimpleNamespace(kwargs={}, state=SimpleNamespace(metadata={}))

    assert executor.should_run(ctx) is False
    assert ctx.state.metadata["research_skipped_reason"] == "phase_executor_should_run_false"


def test_handler_phase_executor_maps_legacy_fail_dict_to_phase_failure():
    executor = HandlerPhaseExecutor(LegacyFailHandler())
    ctx = SimpleNamespace(kwargs={}, state=SimpleNamespace(), pack={})

    result = executor.execute(None, ctx)

    assert result.status == "fail"
    assert result.mutations["reason"] == "hallucination_gate_rejected"


def test_handler_phase_executor_maps_red_test_rejection_to_phase_failure():
    class RedTestRejectedHandler:
        name = "R"
        priority = 30

        def run(self, _state, _pack):
            return {"status": "REJECTED_NO_RED_TEST", "reason": "missing_red_test"}

    executor = HandlerPhaseExecutor(RedTestRejectedHandler())
    ctx = SimpleNamespace(kwargs={}, state=SimpleNamespace(), pack={})

    result = executor.execute(None, ctx)

    assert result.status == "fail"
    assert result.mutations["reason"] == "missing_red_test"


def test_diagnose_executor_failure_records_veto_retry_metadata():
    class DiagnoseVetoHandler:
        name = "D"
        priority = 25

        def run(self, _state, _pack):
            return {"status": "REJECTED", "veto_reason": "unsafe_diagnosis"}

    executor = HandlerPhaseExecutor(DiagnoseVetoHandler())
    ctx = SimpleNamespace(kwargs={}, state=SimpleNamespace(metadata={}), pack={})

    result = executor.execute(None, ctx)

    assert result.status == "fail"
    assert ctx.state.metadata["d_stage_vetoed"] is True
    assert ctx.state.metadata["d_stage_veto_reason"] == "unsafe_diagnosis"
    assert ctx.state.metadata["d_stage_retry_required"] is True


def test_diagnose_binder_preserves_existing_pack_keys(tmp_path, monkeypatch):
    class DiagnoseHandler:
        def __init__(self, *_args, **_kwargs):
            self.name = "D"
            self.priority = 25

        def run(self, _state, _pack):
            return {"diagnosis": "ok"}

    monkeypatch.setattr("nexus.engine.phases.diagnose.DiagnosticPhaseHandler", DiagnoseHandler)
    executor = build_diagnose_executor(tmp_path, tmp_path / ".nexus" / "runs", hub=None)
    ctx = SimpleNamespace(kwargs={}, state=SimpleNamespace(), pack={"task": "keep-me"})

    result = executor.execute(None, ctx)

    assert result.status == "success"
    assert ctx.pack["task"] == "keep-me"
    assert ctx.pack["diagnosis"] == "ok"
    assert ctx.diagnosis_pack == {"diagnosis": "ok"}


def test_crystallize_executor_owns_terminal_side_effects(tmp_path, monkeypatch):
    monkeypatch.setattr("nexus.engine.phases.crystallize.KnowledgeIndex", lambda *_args, **_kwargs: SimpleNamespace(index_reach_evidence=lambda *_a, **_k: None))
    ctx = SimpleNamespace(
        task_id="c-wrap",
        kwargs={},
        tracer=object(),
        pack={},
        state=SimpleNamespace(task_id="c-wrap", metadata={"pipeline_success": True}),
    )
    executor = build_crystallize_executor(tmp_path, tmp_path / ".nexus" / "runs")

    result = executor.execute(None, ctx)

    assert result.status == "success"
    assert ctx.state.metadata["pipeline_terminal_state"] == "SUCCESS"
    assert ctx.state.metadata["pipeline_outcome"]["terminal_state"] == 0
    assert ctx.state.metadata["nexus_outcome_v2"]["terminal_state"] == "SUCCESS"
    assert ctx.pack["crystallize"]["status"] == "COMPLETED"
