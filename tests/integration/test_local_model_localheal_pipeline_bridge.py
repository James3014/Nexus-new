from __future__ import annotations

import shutil
from pathlib import Path

from nexus.services.local_heal.local_model_capability_context import LocalModelCapabilityContext
from nexus.services.local_heal.local_model_capability_executors import (
    LocalHealPipelineCapabilityExecutor,
)


def _make_ctx(topology="local_committee_only"):
    return LocalModelCapabilityContext(
        task_id="t1", source_root="/ws", problem_statement="fix bug",
        target_file="a.py", target_symbol="f", selected_capabilities=("repair_loop",),
        execution_topology=topology, evidence_refs=("ref1",),
        route_context={"run_group": "bridge-test"},
    )


def test_localheal_pipeline_availability_reported():
    """When not in pipeline topology, executor reports module availability."""
    ctx = _make_ctx(topology="local_committee_only")
    r = LocalHealPipelineCapabilityExecutor().execute(ctx)
    assert r.invoked is False
    assert r.telemetries.get("localheal_pipeline_available") is True
    assert r.telemetries.get("committee_orchestrator_available") is True
    assert r.telemetries.get("solid_search_replace_protocol_available") is True
    assert r.telemetries.get("granular_localizer_available") is True
    assert r.telemetries.get("failure_feedback_builder_available") is True
    assert r.telemetries.get("evaluation_gate_available") is True
    assert r.telemetries.get("semantic_retry_available") is True


def test_localheal_pipeline_topology_invokes_modules(tmp_path, monkeypatch):
    """Pipeline topology enters World C but cannot claim completion without evidence."""
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    def prepare_workspace(source_root, _task_id, *, target_file, repro_script):
        source = Path(source_root)
        workspace = source / "world-c-workspace"
        workspace.mkdir()
        shutil.copy2(source / target_file, workspace / target_file)
        return workspace

    monkeypatch.setattr(
        "nexus.services.local_heal.pipeline_isolation.prepare_world_c_workspace",
        prepare_workspace,
    )
    ctx = _make_ctx(topology="localheal_pipeline")
    ctx.source_root = str(tmp_path)
    ctx.failure_feedback = "VERIFIER_FAIL: previous attempt"
    r = LocalHealPipelineCapabilityExecutor().execute(ctx)
    assert r.invoked is True
    assert r.telemetries.get("localheal_pipeline_run_called") is True
    assert r.telemetries.get("localheal_pipeline_actual_execution") is False
    assert r.gate_passed is False
    assert r.telemetries.get("committee_orchestrator_invoked") is True
    assert r.telemetries.get("solid_search_replace_protocol_invoked") is True
    assert r.telemetries.get("granular_localizer_invoked") is True
    assert r.telemetries.get("failure_feedback_builder_invoked") is True
    assert r.telemetries.get("evaluation_gate_invoked") is True


def test_local_committee_only_does_not_invoke_pipeline():
    """local_committee_only should NOT call HealPipeline."""
    ctx = _make_ctx(topology="local_committee_only")
    r = LocalHealPipelineCapabilityExecutor().execute(ctx)
    assert r.invoked is False
    assert "localheal_pipeline_topology_not_selected" in r.failure_reason
    # When not in pipeline topology, invoked_modules keys are not present
    assert "localheal_pipeline_invoked" not in r.telemetries


def test_localheal_pipeline_semantic_retry_available():
    """semantic_retry_available should be True, invoked should be False (no retry in this execution)."""
    ctx = _make_ctx(topology="localheal_pipeline")
    r = LocalHealPipelineCapabilityExecutor().execute(ctx)
    assert r.telemetries.get("semantic_retry_available") is True
    assert r.telemetries.get("semantic_retry_invoked") is False


def test_localheal_pipeline_metadata_keys():
    """All required metadata keys must be present."""
    ctx = _make_ctx(topology="localheal_pipeline")
    r = LocalHealPipelineCapabilityExecutor().execute(ctx)
    required_keys = [
        "localheal_pipeline_available", "localheal_pipeline_invoked",
        "committee_orchestrator_available", "committee_orchestrator_invoked",
        "solid_search_replace_protocol_available", "solid_search_replace_protocol_invoked",
        "granular_localizer_available", "granular_localizer_invoked",
        "failure_feedback_builder_available", "failure_feedback_builder_invoked",
        "evaluation_gate_available", "evaluation_gate_invoked",
        "semantic_retry_available", "semantic_retry_invoked",
    ]
    for key in required_keys:
        assert key in r.telemetries, f"Missing key: {key}"


# --- C9.1: Red tests for actual execution contract ---

def test_localheal_pipeline_requires_actual_execution_not_availability_only():
    """Availability-only bridge must fail causality gate."""
    ctx = _make_ctx(topology="localheal_pipeline")
    r = LocalHealPipelineCapabilityExecutor().execute(ctx)

    # The current implementation should NOT pass gate_passed
    # if it only instantiates modules without calling run/entry
    # This is a RED test - if it passes, the bridge is still availability-only
    if r.telemetries.get("localheal_pipeline_actual_execution") is not True:
        assert r.gate_passed is False, "availability-only bridge must not pass gate"
        assert "path_a_execution_missing" in r.failure_reason or r.failure_reason != ""


def test_local_committee_only_must_not_call_path_a():
    """local_committee_only must NOT invoke Path A run."""
    path_a_called = []

    def spy_run(*args, **kwargs):
        path_a_called.append(True)
        raise AssertionError("Path A run should not be called for local_committee_only")

    from nexus.services.local_heal.pipeline import HealPipeline
    original_run = HealPipeline.run
    HealPipeline.run = spy_run
    try:
        ctx = _make_ctx(topology="local_committee_only")
        r = LocalHealPipelineCapabilityExecutor().execute(ctx)
        assert len(path_a_called) == 0, "Path A run was called for local_committee_only"
        assert r.invoked is False
    finally:
        HealPipeline.run = original_run
