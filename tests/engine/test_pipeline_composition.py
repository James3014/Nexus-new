from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from nexus.core.state_contracts import NexusState
from nexus.engine.phase_plugin import PhaseResult
from nexus.engine.pipeline import NexusPipeline


class _Span:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class FakeExecutor:
    def __init__(self, name: str, mutations: dict):
        self.name = name
        self.priority = {"P": 10, "X": 20, "D": 25, "R": 30, "A": 40, "C": 50}[name]
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
        elif self.name == "C":
            ctx.pack["crystallize"] = self.mutations
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


def test_pipeline_registers_audit_phase_executor(tmp_path):
    executors = {
        "P": FakeExecutor("P", {"plan": "ok"}),
        "X": FakeExecutor("X", {"findings": ["ok"]}),
        "D": FakeExecutor("D", {"diagnosis": "ok"}),
        "A": FakeExecutor("A", {"audit": "ok"}),
    }
    pipeline = NexusPipeline(_engine(tmp_path, executors))

    assert "A" in {plugin.name for plugin in pipeline.registry.get_ordered_plugins()}


def test_pipeline_registers_crystallize_phase_executor(tmp_path):
    executors = {
        "P": FakeExecutor("P", {"plan": "ok"}),
        "X": FakeExecutor("X", {"findings": ["ok"]}),
        "D": FakeExecutor("D", {"diagnosis": "ok"}),
        "C": FakeExecutor("C", {"status": "COMPLETED"}),
    }
    pipeline = NexusPipeline(_engine(tmp_path, executors))

    assert "C" in {plugin.name for plugin in pipeline.registry.get_ordered_plugins()}


def test_pipeline_runs_composed_c_phase_instead_of_direct_crystallize(tmp_path, monkeypatch):
    executors = {
        "P": FakeExecutor("P", {"plan": "ok"}),
        "X": FakeExecutor("X", {"findings": ["ok"]}),
        "D": FakeExecutor("D", {"diagnosis": "ok"}),
        "C": FakeExecutor("C", {"status": "COMPLETED"}),
    }
    pipeline = NexusPipeline(_engine(tmp_path, executors))
    monkeypatch.setattr(pipeline, "_repair_audit_loop", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        pipeline,
        "_stage_crystallize",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("direct C stage should not run when composed C exists")),
    )
    monkeypatch.setattr(pipeline, "_finalize_and_report", lambda _ctx, success, _tracer: success)

    assert pipeline.run("repair vague runtime behavior", task_id="composition-c") is True
    assert executors["C"].calls == 1


def test_repair_audit_loop_runs_composed_r_phase_when_registered(tmp_path, monkeypatch):
    executors = {
        "R": FakeExecutor(
            "R",
            {
                "status": "APPROVED",
                "patch_generated": True,
                "patch_apply_success": True,
                "decision_id": "dec-r",
                "skill_id": "composition-repair",
            },
        )
    }
    pipeline = NexusPipeline(_engine(tmp_path, executors))
    pipeline.engine.max_retries = 1
    ctx = SimpleNamespace(
        dry_run=False,
        task_id="composition-repair",
        task_desc="fix composed repair",
        task_type="bug",
        kwargs={},
        bayesian_params={},
        pack={},
        decision_counter=0,
        accumulator=SimpleNamespace(record=lambda *_args, **_kwargs: None),
        event_store=SimpleNamespace(append=lambda *_args, **_kwargs: None),
        state=NexusState(task_id="composition-repair"),
    )
    tracer = SimpleNamespace(phase_span=lambda *_args, **_kwargs: _Span())
    monkeypatch.setattr(pipeline, "_check_external_interrupt", lambda _ctx: False)
    monkeypatch.setattr(pipeline, "_evaluate_audit_result", lambda *_args, **_kwargs: {"audit_success": True, "status": "APPROVED", "phantom_reason": ""})
    monkeypatch.setattr(
        pipeline,
        "_prepare_repair_context",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy repair context should not run before composed R")),
    )

    assert pipeline._repair_audit_loop(ctx, tracer) is True
    assert executors["R"].calls == 1
    assert ctx.state.metadata["composition_repair_phase_status"] == "APPROVED"


def test_repair_audit_loop_runs_composed_a_phase_before_legacy_audit(tmp_path, monkeypatch):
    executors = {"A": FakeExecutor("A", {"fail": True, "reason": "composition_rejected"})}
    pipeline = NexusPipeline(_engine(tmp_path, executors))
    pipeline.engine.max_retries = 1
    ctx = SimpleNamespace(
        dry_run=False,
        task_id="composition-audit",
        task_type="bug",
        kwargs={},
        bayesian_params={},
        pack={},
        decision_counter=0,
        event_store=SimpleNamespace(append=lambda *_args, **_kwargs: None),
        state=NexusState(task_id="composition-audit"),
    )
    tracer = SimpleNamespace(phase_span=lambda *_args, **_kwargs: None)
    monkeypatch.setattr(pipeline, "_check_external_interrupt", lambda _ctx: False)
    monkeypatch.setattr(
        pipeline,
        "_execute_single_repair",
        lambda *_args, **_kwargs: {
            "status": "APPROVED",
            "result": {"patch_generated": True, "patch_apply_success": True},
            "current_decision_id": "dec-r",
            "current_skill_id": "repair",
        },
    )
    monkeypatch.setattr(
        pipeline,
        "_evaluate_audit_result",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy audit should be blocked by A plugin")),
    )
    monkeypatch.setattr(pipeline, "_build_hallucination_evidence_bundle", lambda _ctx: {"code_artifacts": ["x.py"]})

    assert pipeline._repair_audit_loop(ctx, tracer) is False
    assert executors["A"].calls == 1
    assert ctx.state.metadata["composition_audit_phase_rejection"] == "composition_rejected"


def test_dry_run_repair_respects_composed_a_rejection(tmp_path):
    executors = {"A": FakeExecutor("A", {"fail": True, "reason": "dry_run_audit_rejected"})}
    pipeline = NexusPipeline(_engine(tmp_path, executors))
    ctx = SimpleNamespace(
        dry_run=True,
        task_id="dry-run-audit",
        task_type="bug",
        kwargs={},
        bayesian_params={},
        pack={},
        decision_counter=0,
        event_store=SimpleNamespace(append=lambda *_args, **_kwargs: None),
        state=NexusState(task_id="dry-run-audit"),
    )

    assert pipeline._execute_dry_run_repair(ctx) is False
    assert ctx.state.metadata["composition_audit_phase_rejection"] == "dry_run_audit_rejected"
