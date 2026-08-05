from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from nexus.contracts.canonical_execution import (
    CanonicalTaskContext,
    validate_canonical_execution_binding,
)
from nexus.engine.capability_contracts import CapabilityPlan
from nexus.engine.canonical_execution import plan_canonical_task
from nexus.engine.capability_planner import CapabilityPlanner


class _RecordingPlanner:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def plan(self, **kwargs):
        self.calls.append(kwargs)
        return CapabilityPlan(
            schema_version="nexus_capability_plan_v1",
            selected_capabilities=["artifact_gate", "claim_gate"],
            required_capabilities=["artifact_gate", "claim_gate"],
            optional_capabilities=[],
            conditional_capabilities=[],
            pending_capabilities=[],
            forbidden_capabilities=[],
            constraints=["claim_fail_closed"],
            decision_trace=[],
            replan_trace=[],
            score=8.0,
            planner_mode="dry_run",
            signal_snapshot={"route_truth_source": "CapabilityPlanner"},
            execution_depth="LIGHT",
        )


def test_canonical_task_context_plans_once_and_projects_only_planner_decision(monkeypatch):
    context = CanonicalTaskContext(
        task_id="task-1",
        task_type="bugfix",
        task_desc="Fix a bounded parser defect.",
        route_features={"risk_score": 20, "is_cross_module_task": False},
    )
    planner = _RecordingPlanner()
    monkeypatch.setattr(
        CapabilityPlanner,
        "plan",
        lambda _self, **kwargs: planner.plan(**kwargs),
    )

    decision, projection = plan_canonical_task(context)

    assert len(planner.calls) == 1
    assert planner.calls[0]["route"] == {
        "route_features": {"is_cross_module_task": False, "risk_score": 20}
    }
    assert decision.authority == "CapabilityPlanner"
    assert decision.selected_capabilities == ("artifact_gate", "claim_gate")
    assert projection.execution_decision_authority == "CapabilityPlanner"
    assert projection.decision_hash == decision.decision_hash
    assert projection.context_hash == context.context_hash
    assert len(projection.projection_hash) == 64
    serialized = json.dumps(projection.to_dict(), sort_keys=True)
    for forbidden in ("execution_lane", "provider", "model", "target_worktree"):
        assert forbidden not in serialized


def test_caller_cannot_inject_an_alternate_planner_authority():
    context = CanonicalTaskContext(
        task_id="task-1",
        task_type="bugfix",
        task_desc="Fix a bounded parser defect.",
    )

    with pytest.raises(TypeError):
        plan_canonical_task(context, planner=_RecordingPlanner())


def test_projection_tamper_cannot_change_selected_capabilities(monkeypatch):
    context = CanonicalTaskContext(
        task_id="task-1",
        task_type="bugfix",
        task_desc="Fix a bounded parser defect.",
    )
    planner = _RecordingPlanner()
    monkeypatch.setattr(
        CapabilityPlanner,
        "plan",
        lambda _self, **kwargs: planner.plan(**kwargs),
    )
    decision, projection = plan_canonical_task(context)
    tampered = replace(projection, selected_capabilities=("untrusted_override",))

    with pytest.raises(ValueError, match="projection_capabilities_binding_mismatch"):
        validate_canonical_execution_binding(context, decision, tampered)


def test_projection_tamper_cannot_change_constraints(monkeypatch):
    context = CanonicalTaskContext(
        task_id="task-1",
        task_type="bugfix",
        task_desc="Fix a bounded parser defect.",
    )
    planner = _RecordingPlanner()
    monkeypatch.setattr(
        CapabilityPlanner,
        "plan",
        lambda _self, **kwargs: planner.plan(**kwargs),
    )
    decision, projection = plan_canonical_task(context)
    tampered = replace(projection, constraints=("claim_gate_disabled",))

    with pytest.raises(ValueError, match="projection_constraints_binding_mismatch"):
        validate_canonical_execution_binding(context, decision, tampered)


def test_projection_tamper_cannot_change_execution_depth(monkeypatch):
    context = CanonicalTaskContext(
        task_id="task-1",
        task_type="bugfix",
        task_desc="Fix a bounded parser defect.",
    )
    planner = _RecordingPlanner()
    monkeypatch.setattr(
        CapabilityPlanner,
        "plan",
        lambda _self, **kwargs: planner.plan(**kwargs),
    )
    decision, projection = plan_canonical_task(context)
    tampered = replace(projection, execution_depth="FULL")

    with pytest.raises(ValueError, match="projection_execution_depth_binding_mismatch"):
        validate_canonical_execution_binding(context, decision, tampered)


def test_context_rejects_non_string_keys_with_stable_contract_error():
    with pytest.raises(ValueError, match="canonical_context_key_must_be_string:route_features"):
        CanonicalTaskContext(
            task_id="task-1",
            task_type="bugfix",
            task_desc="Fix a bounded parser defect.",
            route_features={"risk_score": 20, 7: "invalid"},
        )


def test_canonical_seam_rejects_non_capability_plan_output(monkeypatch):
    context = CanonicalTaskContext(
        task_id="task-1",
        task_type="bugfix",
        task_desc="Fix a bounded parser defect.",
    )
    monkeypatch.setattr(CapabilityPlanner, "plan", lambda _self, **_kwargs: {"forged": True})

    with pytest.raises(TypeError, match="capability_planner_must_return_CapabilityPlan"):
        plan_canonical_task(context)


def test_canonical_seam_rejects_plan_without_capability_planner_authority(monkeypatch):
    context = CanonicalTaskContext(
        task_id="task-1",
        task_type="bugfix",
        task_desc="Fix a bounded parser defect.",
    )
    forged = _RecordingPlanner().plan()
    forged.signal_snapshot["route_truth_source"] = "CallerOverride"
    monkeypatch.setattr(CapabilityPlanner, "plan", lambda _self, **_kwargs: forged)

    with pytest.raises(ValueError, match="plan_route_truth_source_must_be_CapabilityPlanner"):
        plan_canonical_task(context)


@pytest.mark.parametrize(
    ("field_name", "forbidden_key"),
    [
        ("route_features", "execution_lane"),
        ("pillars", "provider"),
        ("codeintel", "model"),
        ("phase_trace", "target_worktree"),
        ("budget", "route_override"),
        ("budget", "lifecycle_state"),
        ("budget", "world"),
        ("budget", "worker"),
    ],
)
def test_context_rejects_nested_route_and_execution_authority_overrides(field_name, forbidden_key):
    kwargs = {field_name: {"nested": {forbidden_key: "caller-value"}}}

    with pytest.raises(ValueError, match="canonical_context_route_override_forbidden"):
        CanonicalTaskContext(
            task_id="task-1",
            task_type="bugfix",
            task_desc="Fix a bounded parser defect.",
            **kwargs,
        )


def test_context_is_deeply_immutable_and_hash_is_mapping_order_independent():
    original = {"risk_score": 20, "signals": {"flags": ["a", "b"], "confidence": 0.8}}
    context = CanonicalTaskContext(
        task_id="task-1",
        task_type="bugfix",
        task_desc="Fix a bounded parser defect.",
        route_features=original,
    )
    initial_hash = context.context_hash
    original["risk_score"] = 99
    original["signals"]["flags"].append("mutated")

    reordered = CanonicalTaskContext(
        task_id="task-1",
        task_type="bugfix",
        task_desc="Fix a bounded parser defect.",
        route_features={"signals": {"confidence": 0.8, "flags": ["a", "b"]}, "risk_score": 20},
    )

    assert context.context_hash == initial_hash == reordered.context_hash
    assert context.planner_inputs()["route"]["route_features"]["risk_score"] == 20
    assert context.planner_inputs()["route"]["route_features"]["signals"]["flags"] == ["a", "b"]
    with pytest.raises(TypeError):
        context.route_features["risk_score"] = 30
    with pytest.raises(TypeError):
        context.route_features["signals"]["confidence"] = 0.1


def test_real_capability_planner_produces_bound_canonical_projection():
    context = CanonicalTaskContext(
        task_id="real-planner-task",
        task_type="bugfix",
        task_desc="Fix a bounded parser defect with claim evidence.",
        route_features={"risk_score": 25, "candidate_count": 1},
        budget={"max_cost": 20},
    )

    decision, projection = plan_canonical_task(context)

    validate_canonical_execution_binding(context, decision, projection)
    assert decision.authority == "CapabilityPlanner"
    assert {"artifact_gate", "claim_gate"} <= set(decision.selected_capabilities)
    assert projection.decision_hash == decision.decision_hash


def test_context_budget_rejects_policy_or_memory_injection():
    with pytest.raises(ValueError, match="canonical_context_budget_key_forbidden:learning_policy"):
        CanonicalTaskContext(
            task_id="task-1",
            task_type="bugfix",
            task_desc="Fix a bounded parser defect.",
            budget={"learning_policy": {"promoted_capabilities": ["swarm"]}},
        )


@pytest.mark.parametrize(
    ("field_name", "message"),
    [
        ("plan_schema_version", "plan_schema_version_required"),
        ("planner_mode", "planner_mode_required"),
    ],
)
def test_execution_decision_requires_planner_identity_fields(monkeypatch, field_name, message):
    context = CanonicalTaskContext(
        task_id="task-1",
        task_type="bugfix",
        task_desc="Fix a bounded parser defect.",
    )
    planner = _RecordingPlanner()
    monkeypatch.setattr(
        CapabilityPlanner,
        "plan",
        lambda _self, **kwargs: planner.plan(**kwargs),
    )
    decision, _projection = plan_canonical_task(context)

    with pytest.raises(ValueError, match=message):
        replace(decision, **{field_name: ""})


def test_canonical_seam_has_one_planner_call_and_no_forbidden_runtime_dependencies():
    source_path = Path(__file__).parents[2] / "nexus/engine/canonical_execution.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    planner_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "plan"
    ]

    assert len(planner_calls) == 1
    assert imported_modules == {
        "__future__",
        "nexus.contracts.canonical_execution",
        "nexus.engine.capability_contracts",
        "nexus.engine.capability_planner",
    }
    lowered = source.lower()
    for forbidden in (
        "execution_lane",
        "provider",
        "target_worktree",
        "local_heal",
        "candidate",
        "lifecycle",
        "unified_mcp_gateway",
    ):
        assert forbidden not in lowered
