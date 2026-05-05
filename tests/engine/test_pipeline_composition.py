from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from nexus.engine.phase_plugin import PhaseResult
from nexus.engine.pipeline import NexusPipeline


class FakeExecutor:
    def __init__(self, name: str, mutations: dict):
        self.name = name
        self.priority = {"P": 10, "X": 20, "D": 25}[name]
        self.mutations = mutations
        self.calls = 0

    def should_run(self, _ctx):
        return True

    def execute(self, _pipeline, ctx):
        self.calls += 1
        if self.name == "P":
            ctx.prediction = self.mutations
            ctx.state.metadata["research_route"] = {"should_research": True}
        elif self.name == "X":
            ctx.research_pack = self.mutations
        elif self.name == "D":
            ctx.pack = self.mutations
        return PhaseResult(status="success", mutations=self.mutations, events=[])


def _engine(tmp_path: Path, executors: dict):
    engine = MagicMock()
    engine.project_root = tmp_path
    engine.run_dir = tmp_path / ".nexus" / "runs"
    engine.run_dir.mkdir(parents=True, exist_ok=True)
    engine.phase_executors = executors
    engine.phases = {"P": "legacy-plan", "X": "legacy-research", "D": "legacy-diagnose"}
    engine.policy_manager.apply_policy_to_state = lambda *_args, **_kwargs: None
    engine.state_io.save_global_state = lambda *_args, **_kwargs: None
    engine.commander.next_step = lambda **_kwargs: None
    engine.accumulator = SimpleNamespace(record=lambda *_args, **_kwargs: None)
    engine.health_evaluator = SimpleNamespace(evaluate=lambda *_args, **_kwargs: 100.0)
    engine.research_policy = MagicMock()
    engine.hub = MagicMock()
    engine._add_step_to_history = lambda *_args, **_kwargs: None
    return engine


def test_pipeline_prefers_phase_executor_composition_over_mixin_methods(tmp_path, monkeypatch):
    executors = {
        "P": FakeExecutor("P", {"plan": "ok"}),
        "X": FakeExecutor("X", {"findings": ["ok"]}),
        "D": FakeExecutor("D", {"diagnosis": "ok"}),
    }
    pipeline = NexusPipeline(_engine(tmp_path, executors))

    def fail_legacy_stage(*_args, **_kwargs):
        raise AssertionError("legacy mixin stage should not run when phase_executors are provided")

    monkeypatch.setattr(pipeline, "_stage_plan", fail_legacy_stage)
    monkeypatch.setattr(pipeline, "_stage_research", fail_legacy_stage)
    monkeypatch.setattr(pipeline, "_stage_diagnose", fail_legacy_stage)
    monkeypatch.setattr(pipeline, "_repair_audit_loop", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(pipeline, "_stage_crystallize", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(pipeline, "_finalize_and_report", lambda _ctx, success, _tracer: success)

    assert pipeline.run("repair vague runtime behavior", task_id="composition-1") is True
    assert executors["P"].calls == 1
    assert executors["X"].calls == 1
    assert executors["D"].calls == 1
