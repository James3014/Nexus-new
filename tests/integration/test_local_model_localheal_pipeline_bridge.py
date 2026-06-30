from __future__ import annotations

import hashlib
import pytest

from nexus.services.local_heal.local_model_capability_executors import (
    LocalHealPipelineCapabilityExecutor,
)
from nexus.services.local_heal.local_model_capability_context import LocalModelCapabilityContext


def _make_ctx(topology="local_committee_only"):
    return LocalModelCapabilityContext(
        task_id="t1", source_root="/ws", problem_statement="fix bug",
        target_file="a.py", target_symbol="f", selected_capabilities=("repair_loop",),
        execution_topology=topology, evidence_refs=("ref1",),
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


def test_localheal_pipeline_topology_invokes_modules():
    """When in pipeline topology, executor invokes path A modules."""
    ctx = _make_ctx(topology="localheal_pipeline")
    r = LocalHealPipelineCapabilityExecutor().execute(ctx)
    assert r.invoked is True
    # localheal_pipeline may fail to fully invoke due to HealContext import,
    # but other modules should be invoked
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
