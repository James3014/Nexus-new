from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from nexus.contracts.canonical_execution import (
    CanonicalPlanningBundle,
    CanonicalTaskContext,
    validate_canonical_execution_binding,
)
from nexus.engine.canonical_execution import (
    plan_canonical_task,
    plan_canonical_task_bundle,
    replan_canonical_task_bundle,
)
from nexus.engine.capability_contracts import CapabilityPlan, ExecutionReplanAuthorization
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
        "route_features": {"is_cross_module_task": False, "risk_score": 20},
        "workforce_admission_enabled": True,
        "online_enabled": True,
        "local_enabled": False,
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


def test_canonical_context_allows_code_target_facts_but_not_target_authority() -> None:
    context = CanonicalTaskContext(
        task_id="task-code-target-facts",
        task_type="bugfix",
        task_desc="Inspect one bounded symbol.",
        codeintel={"target_file": "nexus/example.py", "target_symbol": "parse"},
    )

    assert context.to_dict()["codeintel"] == {
        "target_file": "nexus/example.py",
        "target_symbol": "parse",
    }
    with pytest.raises(ValueError, match="canonical_context_route_override_forbidden"):
        CanonicalTaskContext(
            task_id="task-target-authority",
            task_type="bugfix",
            task_desc="Reject a Target worktree selector.",
            codeintel={"target_worktree": "/tmp/forged-target"},
        )


def test_candidate_generation_only_requires_explicit_non_mutation() -> None:
    context = CanonicalTaskContext(
        task_id="task-candidate-only",
        task_type="candidate_generation",
        task_desc="Produce one bounded candidate without mutation authority.",
        task_facts={
            "candidate_generation_only": True,
            "mutation_requested": False,
        },
    )

    assert context.to_dict()["task_facts"] == {
        "candidate_generation_only": True,
        "mutation_requested": False,
    }
    assert context.planner_inputs()["route"]["topology_facts"] == {
        "candidate_generation_only": True,
        "mutation_requested": False,
    }


@pytest.mark.parametrize(
    "task_facts",
    [
        {"candidate_generation_only": True},
        {"candidate_generation_only": True, "mutation_requested": True},
        {"candidate_generation_only": "true", "mutation_requested": False},
    ],
)
def test_candidate_generation_only_rejects_missing_contradictory_or_malformed_facts(
    task_facts,
) -> None:
    with pytest.raises(ValueError, match="candidate_generation_only|task_fact_must_be_bool"):
        CanonicalTaskContext(
            task_id="task-candidate-only-invalid",
            task_type="candidate_generation",
            task_desc="Reject an invalid candidate-only contract.",
            task_facts=task_facts,
        )


def test_canonical_context_allows_formal_route_receipt_evidence() -> None:
    context = CanonicalTaskContext(
        task_id="task-route-receipt-evidence",
        task_type="audit",
        task_desc="Carry observed route evidence without selecting a route.",
        codeintel={
            "formal_route_receipts": [
                {
                    "route": "mainchain",
                    "evidence_present": True,
                    "gate_passed": True,
                }
            ]
        },
    )

    assert context.to_dict()["codeintel"]["formal_route_receipts"] == [
        {
            "route": "mainchain",
            "evidence_present": True,
            "gate_passed": True,
        }
    ]


def test_canonical_planning_bundle_binds_the_exact_plan_without_replanning(monkeypatch):
    context = CanonicalTaskContext(
        task_id="task-bundle-1",
        task_type="bugfix",
        task_desc="Fix one bounded parser defect.",
        route_features={"risk_score": 20},
    )
    planner = _RecordingPlanner()
    monkeypatch.setattr(
        CapabilityPlanner,
        "plan",
        lambda _self, **kwargs: planner.plan(**kwargs),
    )

    bundle = plan_canonical_task_bundle(context)

    assert len(planner.calls) == 1
    assert bundle.context is context
    assert bundle.plan.to_dict()["selected_capabilities"] == ["artifact_gate", "claim_gate"]
    assert bundle.decision.plan_hash == bundle.plan_hash
    assert bundle.projection.plan_hash == bundle.plan_hash
    assert bundle.to_dict()["projection_hash"] == bundle.projection.projection_hash


def test_canonical_planning_bundle_cannot_be_mutated_or_rebound_to_another_plan(monkeypatch):
    context = CanonicalTaskContext(
        task_id="task-bundle-tamper",
        task_type="bugfix",
        task_desc="Keep the runtime plan bound.",
    )
    monkeypatch.setattr(CapabilityPlanner, "plan", lambda _self, **_kwargs: _RecordingPlanner().plan())
    bundle = plan_canonical_task_bundle(context)
    original_hash = bundle.plan_hash

    detached_plan = bundle.plan
    detached_plan.selected_capabilities.append("untrusted_override")

    assert bundle.plan.selected_capabilities == ["artifact_gate", "claim_gate"]
    assert bundle.plan_hash == original_hash
    tampered_payload = bundle.to_dict()["plan_payload"]
    tampered_payload["selected_capabilities"] = ["untrusted_override"]
    with pytest.raises(ValueError, match="bundle_plan_hash_binding_mismatch"):
        replace(bundle, plan_payload=tampered_payload)


def test_canonical_context_requires_workforce_demands_for_available_execution_channels(monkeypatch):
    context = CanonicalTaskContext(
        task_id="task-workforce-channels",
        task_type="bugfix",
        task_desc="Run one shared Online and Local decision.",
        execution_channels=("local", "online"),
    )
    planner = _RecordingPlanner()
    monkeypatch.setattr(
        CapabilityPlanner,
        "plan",
        lambda _self, **kwargs: planner.plan(**kwargs),
    )

    plan_canonical_task_bundle(context)

    assert planner.calls[0]["route"] == {
        "route_features": {},
        "workforce_admission_enabled": True,
        "online_enabled": True,
        "local_enabled": True,
    }


def test_canonical_replan_builds_one_fresh_bundle_from_explicit_authorization(monkeypatch):
    context = CanonicalTaskContext(
        task_id="task-replan-bundle",
        task_type="bugfix",
        task_desc="Replan only after verified failure.",
    )
    authorization = ExecutionReplanAuthorization(
        task_id=context.task_id,
        workspace_revision="rev-replan-bundle",
        source_planner_decision_id="1" * 64,
        source_replan_request_id="sha256:" + "2" * 64,
        source_receipt_hash="3" * 64,
        source_run_anchor_hash="4" * 64,
        requested_execution_depth="STANDARD",
    )
    planner = _RecordingPlanner()
    monkeypatch.setattr(
        CapabilityPlanner,
        "plan",
        lambda _self, **kwargs: planner.plan(**kwargs),
    )

    bundle = replan_canonical_task_bundle(context, authorization)

    assert len(planner.calls) == 1
    assert planner.calls[0]["replan_authorization"] is authorization
    assert bundle.context.context_hash == context.context_hash
    assert bundle.decision.plan_hash == bundle.plan_hash


def test_canonical_planning_bundle_wire_round_trip_rejects_tamper(monkeypatch):
    context = CanonicalTaskContext(
        task_id="task-bundle-wire",
        task_type="bugfix",
        task_desc="Carry the exact plan across ingress.",
    )
    monkeypatch.setattr(CapabilityPlanner, "plan", lambda _self, **_kwargs: _RecordingPlanner().plan())
    bundle = plan_canonical_task_bundle(context)

    restored = CanonicalPlanningBundle.from_dict(bundle.to_dict())

    assert restored.to_dict() == bundle.to_dict()
    tampered = bundle.to_dict()
    tampered["plan_payload"]["score"] = 999
    with pytest.raises(ValueError, match="bundle_plan_hash_binding_mismatch"):
        CanonicalPlanningBundle.from_dict(tampered)


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
