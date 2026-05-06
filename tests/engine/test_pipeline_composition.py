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
            metadata_updates = self.mutations.get("metadata_updates")
            if isinstance(metadata_updates, dict):
                ctx.state.metadata.update(metadata_updates)
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


def test_pipeline_emits_typed_phase_transition_events(tmp_path, monkeypatch):
    executors = {
        "P": FakeExecutor("P", {"plan": "ok"}),
        "X": FakeExecutor("X", {"findings": ["ok"]}),
        "D": FakeExecutor("D", {"diagnosis": "ok"}),
    }
    pipeline = NexusPipeline(_engine(tmp_path, executors))
    seen = {}
    monkeypatch.setattr(pipeline, "_repair_audit_loop", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(pipeline, "_stage_crystallize", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(pipeline, "_finalize_and_report", lambda ctx, success, _tracer: seen.update(events=ctx.event_store.get_events()) or success)

    assert pipeline.run("repair vague runtime behavior", task_id="typed-events") is True

    event_types = [event.event_type for event in seen["events"]]
    assert "phase_transition" in event_types
    assert "lifecycle_hook" in event_types
    assert "phase_start" not in event_types
    assert "phase_end" not in event_types
    assert "lifecycle_pre" not in event_types


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


def test_pipeline_falls_back_when_composed_c_lacks_terminal_side_effects(tmp_path, monkeypatch):
    executors = {
        "P": FakeExecutor("P", {"plan": "ok"}),
        "X": FakeExecutor("X", {"findings": ["ok"]}),
        "D": FakeExecutor("D", {"diagnosis": "ok"}),
        "C": FakeExecutor("C", {"status": "COMPLETED"}),
    }
    pipeline = NexusPipeline(_engine(tmp_path, executors))
    monkeypatch.setattr(pipeline, "_repair_audit_loop", lambda *_args, **_kwargs: True)
    fallback_calls = []
    monkeypatch.setattr(pipeline, "_stage_crystallize", lambda ctx, success, _tracer: fallback_calls.append((ctx.task_id, success)))
    monkeypatch.setattr(pipeline, "_finalize_and_report", lambda _ctx, success, _tracer: success)

    assert pipeline.run("repair vague runtime behavior", task_id="composition-c") is True
    assert executors["C"].calls == 1
    assert fallback_calls == [("composition-c", True)]


def test_pipeline_accepts_composed_c_only_when_terminal_side_effects_exist(tmp_path, monkeypatch):
    executors = {
        "P": FakeExecutor("P", {"plan": "ok"}),
        "X": FakeExecutor("X", {"findings": ["ok"]}),
        "D": FakeExecutor("D", {"diagnosis": "ok"}),
        "C": FakeExecutor(
            "C",
            {
                "status": "COMPLETED",
                "metadata_updates": {
                    "pipeline_terminal_state": "SUCCESS",
                    "pipeline_outcome": {"terminal_state": "SUCCESS"},
                    "nexus_outcome_v2": {"terminal_state": "SUCCESS"},
                },
            },
        ),
    }
    pipeline = NexusPipeline(_engine(tmp_path, executors))
    monkeypatch.setattr(pipeline, "_repair_audit_loop", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        pipeline,
        "_stage_crystallize",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("verified composed C must not fallback to legacy C")),
    )
    seen = {}
    monkeypatch.setattr(pipeline, "_finalize_and_report", lambda ctx, success, _tracer: seen.update(ctx.state.metadata) or success)

    assert pipeline.run("repair vague runtime behavior", task_id="composition-c-verified") is True
    assert executors["C"].calls == 1
    assert seen["composition_crystallize_side_effects_verified"] is True


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
    pregate_calls = []
    evidence_calls = []
    monkeypatch.setattr(
        pipeline,
        "_run_pregate_if_needed",
        lambda _ctx, status, result: pregate_calls.append((status, result)) or status,
    )
    monkeypatch.setattr(
        pipeline,
        "_write_hallucination_evidence_bundle",
        lambda _ctx: evidence_calls.append(_ctx.task_id) or (tmp_path / "evidence.json"),
    )
    monkeypatch.setattr(
        pipeline,
        "_prepare_repair_context",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy repair context should not run before composed R")),
    )

    assert pipeline._repair_audit_loop(ctx, tracer) is True
    assert executors["R"].calls == 1
    assert ctx.state.metadata["composition_repair_phase_status"] == "APPROVED"
    assert ctx.state.metadata["last_patch_generated"] is True
    assert ctx.state.metadata["phase_decisions"]["R"] == "dec-r"
    assert ctx.state.metadata["phase_skills"]["R"] == "composition-repair"
    assert pregate_calls == [("APPROVED", executors["R"].mutations)]
    assert evidence_calls == ["composition-repair"]


def test_repair_audit_loop_composed_r_rejection_skips_pregate_and_evidence(tmp_path, monkeypatch):
    executors = {
        "R": FakeExecutor(
            "R",
            {
                "status": "REJECTED_NO_RED_TEST",
                "reason": "missing_red_test",
                "decision_id": "dec-r",
                "skill_id": "composition-repair",
            },
        )
    }
    pipeline = NexusPipeline(_engine(tmp_path, executors))
    pipeline.engine.max_retries = 1
    ctx = SimpleNamespace(
        dry_run=False,
        task_id="composition-repair-rejected",
        task_desc="fix composed repair",
        task_type="bug",
        kwargs={},
        bayesian_params={},
        pack={},
        decision_counter=0,
        accumulator=SimpleNamespace(record=lambda *_args, **_kwargs: None),
        event_store=SimpleNamespace(append=lambda *_args, **_kwargs: None),
        state=NexusState(task_id="composition-repair-rejected"),
    )
    tracer = SimpleNamespace(phase_span=lambda *_args, **_kwargs: _Span())
    monkeypatch.setattr(pipeline, "_check_external_interrupt", lambda _ctx: False)
    monkeypatch.setattr(
        pipeline,
        "_run_pregate_if_needed",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("rejected composed R must not run pregate")),
    )
    monkeypatch.setattr(
        pipeline,
        "_write_hallucination_evidence_bundle",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("rejected composed R must not write evidence")),
    )
    monkeypatch.setattr(
        pipeline,
        "_evaluate_audit_result",
        lambda *_args, **_kwargs: {"audit_success": False, "status": "REJECTED", "phantom_reason": ""},
    )
    monkeypatch.setattr(pipeline, "_handle_escalation", lambda *_args, **_kwargs: False)

    assert pipeline._repair_audit_loop(ctx, tracer) is False
    assert executors["R"].calls == 1
    assert ctx.state.metadata["composition_repair_phase_status"] == "REJECTED_NO_RED_TEST"
    assert ctx.state.metadata["phase_decisions"]["R"] == "dec-r"
    assert ctx.state.metadata["phase_skills"]["R"] == "composition-repair"


def test_repair_audit_loop_composed_r_uses_nested_result_status(tmp_path, monkeypatch):
    nested_result = {
        "status": "APPROVED",
        "patch_generated": True,
        "patch_apply_success": True,
    }
    executors = {"R": FakeExecutor("R", {"result_object": nested_result})}
    pipeline = NexusPipeline(_engine(tmp_path, executors))
    pipeline.engine.max_retries = 1
    ctx = SimpleNamespace(
        dry_run=False,
        task_id="composition-repair-nested",
        task_desc="fix composed repair",
        task_type="bug",
        kwargs={},
        bayesian_params={},
        pack={},
        decision_counter=0,
        accumulator=SimpleNamespace(record=lambda *_args, **_kwargs: None),
        event_store=SimpleNamespace(append=lambda *_args, **_kwargs: None),
        state=NexusState(task_id="composition-repair-nested"),
    )
    tracer = SimpleNamespace(phase_span=lambda *_args, **_kwargs: _Span())
    pregate_calls = []
    monkeypatch.setattr(pipeline, "_check_external_interrupt", lambda _ctx: False)
    monkeypatch.setattr(pipeline, "_register_phase_decision", lambda *_args, **_kwargs: "dec-r-fallback")
    monkeypatch.setattr(
        pipeline,
        "_run_pregate_if_needed",
        lambda _ctx, status, result: pregate_calls.append((status, result)) or status,
    )
    monkeypatch.setattr(pipeline, "_write_hallucination_evidence_bundle", lambda _ctx: tmp_path / "evidence.json")
    monkeypatch.setattr(
        pipeline,
        "_evaluate_audit_result",
        lambda *_args, **_kwargs: {"audit_success": True, "status": "APPROVED", "phantom_reason": ""},
    )

    assert pipeline._repair_audit_loop(ctx, tracer) is True
    assert ctx.state.metadata["composition_repair_phase_status"] == "APPROVED"
    assert ctx.state.metadata["last_patch_generated"] is True
    assert ctx.state.metadata["phase_decisions"]["R"] == "dec-r-fallback"
    assert ctx.state.metadata["phase_skills"]["R"] == "composition-repair"
    assert pregate_calls == [("APPROVED", nested_result)]


def test_repair_audit_loop_composed_r_without_review_status_fails_closed(tmp_path, monkeypatch):
    executors = {"R": FakeExecutor("R", {"result_object": {"patch_generated": True}})}
    pipeline = NexusPipeline(_engine(tmp_path, executors))
    pipeline.engine.max_retries = 1
    ctx = SimpleNamespace(
        dry_run=False,
        task_id="composition-repair-no-status",
        task_desc="fix composed repair",
        task_type="bug",
        kwargs={},
        bayesian_params={},
        pack={},
        decision_counter=0,
        accumulator=SimpleNamespace(record=lambda *_args, **_kwargs: None),
        event_store=SimpleNamespace(append=lambda *_args, **_kwargs: None),
        state=NexusState(task_id="composition-repair-no-status"),
    )
    tracer = SimpleNamespace(phase_span=lambda *_args, **_kwargs: _Span())
    monkeypatch.setattr(pipeline, "_check_external_interrupt", lambda _ctx: False)
    monkeypatch.setattr(pipeline, "_register_phase_decision", lambda *_args, **_kwargs: "dec-r-fail-closed")
    monkeypatch.setattr(
        pipeline,
        "_run_pregate_if_needed",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("status-less composed R must not run pregate")),
    )
    monkeypatch.setattr(
        pipeline,
        "_write_hallucination_evidence_bundle",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("status-less composed R must not write evidence")),
    )
    monkeypatch.setattr(
        pipeline,
        "_evaluate_audit_result",
        lambda *_args, **_kwargs: {"audit_success": False, "status": "REJECTED", "phantom_reason": ""},
    )
    monkeypatch.setattr(pipeline, "_handle_escalation", lambda *_args, **_kwargs: False)

    assert pipeline._repair_audit_loop(ctx, tracer) is False
    assert executors["R"].calls == 1
    assert ctx.state.metadata["composition_repair_phase_status"] == "REJECTED"
    assert ctx.state.metadata["phase_decisions"]["R"] == "dec-r-fail-closed"
    assert ctx.state.metadata["phase_skills"]["R"] == "composition-repair"


def test_repair_audit_loop_runs_composed_a_phase_before_legacy_audit(tmp_path, monkeypatch):
    executors = {
        "A": FakeExecutor(
            "A",
            {
                "fail": True,
                "reason": "composition_rejected",
                "decision_id": "dec-a",
                "skill_id": "composition-audit",
            },
        )
    }
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
    assert ctx.state.metadata["phase_decisions"]["A"] == "dec-a"
    assert ctx.state.metadata["phase_skills"]["A"] == "composition-audit"


def test_repair_audit_loop_composed_a_accepts_without_legacy_audit(tmp_path, monkeypatch):
    executors = {"A": FakeExecutor("A", {"status": "APPROVED", "decision_id": "dec-a-pass", "skill_id": "composition-audit"})}
    pipeline = NexusPipeline(_engine(tmp_path, executors))
    pipeline.engine.max_retries = 1
    ctx = SimpleNamespace(
        dry_run=False,
        task_id="composition-audit-pass",
        task_type="bug",
        kwargs={},
        bayesian_params={},
        pack={},
        decision_counter=0,
        event_store=SimpleNamespace(append=lambda *_args, **_kwargs: None),
        state=NexusState(task_id="composition-audit-pass"),
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
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy audit should not run")),
    )
    monkeypatch.setattr(pipeline, "_build_hallucination_evidence_bundle", lambda _ctx: {"code_artifacts": ["x.py"]})

    assert pipeline._repair_audit_loop(ctx, tracer) is True
    assert executors["A"].calls == 1
    assert ctx.state.metadata["composition_audit_phase_status"] == "APPROVED"
    assert ctx.state.metadata["phase_decisions"]["A"] == "dec-a-pass"


def test_repair_audit_loop_composed_a_rejects_status_without_fail_flag(tmp_path, monkeypatch):
    executors = {"A": FakeExecutor("A", {"status": "REJECTED", "reason": "logic_mismatch"})}
    pipeline = NexusPipeline(_engine(tmp_path, executors))
    pipeline.engine.max_retries = 1
    history_calls = []
    outcome_calls = []
    pipeline.engine._add_step_to_history = lambda _state, phase, metadata: history_calls.append((phase, metadata))
    monkeypatch.setattr(
        pipeline,
        "_record_repair_outcome_event",
        lambda *args, **_kwargs: outcome_calls.append(args),
    )
    ctx = SimpleNamespace(
        dry_run=False,
        task_id="composition-audit-status-rejected",
        task_type="bug",
        kwargs={},
        bayesian_params={},
        pack={},
        decision_counter=0,
        event_store=SimpleNamespace(append=lambda *_args, **_kwargs: None),
        state=NexusState(task_id="composition-audit-status-rejected"),
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
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("rejected composed A must block legacy audit")),
    )
    monkeypatch.setattr(pipeline, "_build_hallucination_evidence_bundle", lambda _ctx: {"code_artifacts": ["x.py"]})
    monkeypatch.setattr(pipeline, "_register_phase_decision", lambda *_args, **_kwargs: "dec-a-fallback")

    assert pipeline._repair_audit_loop(ctx, tracer) is False
    assert ctx.state.metadata["composition_audit_phase_status"] == "REJECTED"
    assert ctx.state.metadata["composition_audit_phase_rejection"] == "logic_mismatch"
    assert ctx.state.metadata["phase_decisions"]["A"] == "dec-a-fallback"
    assert ctx.state.metadata["phase_skills"]["A"] == "composition-audit"
    assert ctx.state.metadata["last_audit_decision_id"] == "dec-a-fallback"
    assert ctx.state.metadata["last_repair_decision_id"] == "dec-r"
    assert ctx.state.metadata["anti_hallucination_checks"] == 1
    assert ctx.state.metadata["anti_hallucination_block_count"] == 1
    assert ctx.state.metadata["evidence_trust_rejection"] is True
    assert history_calls == [
        (
            "A",
            {
                "status": "REJECTED",
                "decision_id": "dec-a-fallback",
                "skill_id": "composition-audit",
                "composition_phase": True,
            },
        )
    ]
    assert outcome_calls[0][1:6] == (1, False, "logic_mismatch", {"patch_generated": True, "patch_apply_success": True}, "dec-r")


def test_repair_audit_loop_composed_a_rejects_false_audit_success(tmp_path, monkeypatch):
    executors = {"A": FakeExecutor("A", {"audit_success": False, "reason": "evidence_low_trust"})}
    pipeline = NexusPipeline(_engine(tmp_path, executors))
    pipeline.engine.max_retries = 1
    ctx = SimpleNamespace(
        dry_run=False,
        task_id="composition-audit-false-success",
        task_type="bug",
        kwargs={},
        bayesian_params={},
        pack={},
        decision_counter=0,
        event_store=SimpleNamespace(append=lambda *_args, **_kwargs: None),
        state=NexusState(task_id="composition-audit-false-success"),
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
    monkeypatch.setattr(pipeline, "_build_hallucination_evidence_bundle", lambda _ctx: {"code_artifacts": ["x.py"]})
    monkeypatch.setattr(pipeline, "_handle_escalation", lambda *_args, **_kwargs: False)

    assert pipeline._repair_audit_loop(ctx, tracer) is False
    assert ctx.state.metadata["composition_audit_phase_status"] == "REJECTED"
    assert ctx.state.metadata["composition_audit_phase_rejection"] == "evidence_low_trust"


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
