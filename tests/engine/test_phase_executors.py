from __future__ import annotations

from types import SimpleNamespace

from nexus.engine.phase_executors import HandlerPhaseExecutor, build_crystallize_executor
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


def test_crystallize_executor_wraps_existing_rich_pipeline_method(tmp_path):
    calls = []

    class Pipeline:
        def _stage_crystallize(self, ctx, success, tracer):
            calls.append((ctx.task_id, success, tracer))
            ctx.state.metadata["rich_crystallize_ran"] = True

    ctx = SimpleNamespace(
        task_id="c-wrap",
        kwargs={},
        tracer=object(),
        pack={},
        state=SimpleNamespace(metadata={"pipeline_success": True}),
    )
    executor = build_crystallize_executor(tmp_path, tmp_path / ".nexus" / "runs")

    result = executor.execute(Pipeline(), ctx)

    assert result.status == "success"
    assert calls == [("c-wrap", True, ctx.tracer)]
    assert ctx.state.metadata["rich_crystallize_ran"] is True
    assert ctx.pack["crystallize"]["status"] == "COMPLETED"
