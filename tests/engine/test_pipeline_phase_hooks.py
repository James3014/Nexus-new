from __future__ import annotations

from types import SimpleNamespace

from nexus.core.state_contracts import NexusState
from nexus.engine.phase_plugin import PhaseResult
from nexus.engine.pipeline import PipelineContext, NexusPipeline


def _context(events):
    state = NexusState(task_id="hooks-1")
    state.metadata["runtime_phase"] = "S"
    return PipelineContext(
        state=state,
        task_desc="phase hooks",
        task_type="test",
        task_id="hooks-1",
        kwargs={},
        dry_run=False,
        hub=None,
        accumulator=None,
        health_evaluator=None,
        research_policy=None,
        event_store=SimpleNamespace(append=events.append),
    )


def test_formulation_phase_emits_start_end_and_phase_receipt():
    events = []
    pipeline = NexusPipeline(SimpleNamespace(phases={}, phase_executors={}))
    ctx = _context(events)
    plugin = SimpleNamespace(
        name="P",
        required_artifacts=lambda: (),
        provided_artifacts=lambda: (),
        execute=lambda _pipeline, _ctx: PhaseResult(status="success", mutations={"plan": "ok"}, events=[]),
    )

    assert pipeline._run_formulation_plugin(plugin, ctx) is True
    hooks = [event.payload["hook"] for event in events if event.event_type == "lifecycle_hook"]
    assert hooks == ["on_phase_start", "on_phase_end"]
    receipt = ctx.state.metadata["phase_receipts"][0]
    assert receipt["phase"] == "P"
    assert receipt["status"] == "SUCCESS"
    assert receipt["input_hash"]
    assert receipt["output_hash"]


def test_observer_failure_is_fail_open_but_receipt_guard_is_not():
    pipeline = NexusPipeline(SimpleNamespace(phases={}, phase_executors={}))

    class BrokenStore:
        def append(self, _event):
            raise OSError("telemetry offline")

    ctx = _context([])
    ctx.event_store = BrokenStore()
    pipeline._emit_phase_observer(ctx, "P", "on_phase_start")
    assert ctx.state.metadata.get("phase_receipts", []) == []
