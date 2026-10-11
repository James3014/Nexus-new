"""#1737: CapabilityPlanner is the single decision point for mainchain gate selection."""

from __future__ import annotations

from typing import Any

import pytest

from nexus.engine.capability_planner import CapabilityPlanner
from nexus.services.mainchain_entry import build_mainchain_capability_invokers

GATES = ("pregate", "plan_quality_gate", "forecast_gate")


def _plan_dict(task_type: str, *, risk: int = 10, **features: Any) -> dict[str, Any]:
    return (
        CapabilityPlanner()
        .plan(
            task_desc="Update the helper module.",
            task_type=task_type,
            route={
                "recommended_flow": "baseline",
                "route_features": {"risk_score": risk, "candidate_count": 1, **features},
            },
        )
        .to_dict()
    )


def _plan(task_type: str, *, risk: int = 10, **features: Any) -> set[str]:
    return set(_plan_dict(task_type, risk=risk, **features)["selected_capabilities"])


@pytest.mark.parametrize(
    "task_type",
    [
        "feature",
        "public_feature",
        "refactor",
        "public_refactor",
        "code_change",
        "repair",
        "platform_integration",
    ],
)
def test_code_mutation_task_classes_select_pregate_and_plan_quality_gate(task_type: str) -> None:
    selected = _plan(task_type)
    assert {"pregate", "plan_quality_gate"} <= selected
    assert "forecast_gate" not in selected


def test_cross_module_refactor_class_selects_forecast_gate_for_multi_step() -> None:
    selected = _plan("cross_module_refactor_swarm", is_cross_module_task=True)
    assert set(GATES) <= selected


@pytest.mark.parametrize(
    "task_type", ["bug", "bugfix", "docs_fix", "public_docs_code_sync", "research", "review"]
)
def test_low_risk_non_mutation_task_classes_select_no_mainchain_gate(task_type: str) -> None:
    assert not set(GATES) & _plan(task_type)


@pytest.mark.parametrize("task_type", ["bug", "docs_fix", "research", "feature"])
def test_high_risk_selects_all_three_gates_for_any_task_class(task_type: str) -> None:
    assert set(GATES) <= _plan(task_type, risk=85)


def test_selection_is_deterministic_and_explained_in_decision_trace() -> None:
    assert _plan("feature", risk=85) == _plan("feature", risk=85)
    trace = {
        item["capability"]: item["reasons"]
        for item in _plan_dict("feature", risk=85)["decision_trace"]
    }
    assert "mainchain_code_mutation_task_class" in trace["pregate"]
    assert "mainchain_high_risk" in trace["forecast_gate"]


def test_planner_never_advertises_retired_autonomic_router() -> None:
    for task_type, risk in (("feature", 10), ("cross_module_refactor_swarm", 95), ("bug", 85)):
        assert "autonomic_router" not in _plan(task_type, risk=risk, is_cross_module_task=True)


def test_selected_gates_execute_through_mainchain_invokers_with_non_skip_receipts(tmp_path) -> None:
    selected = _plan("cross_module_refactor_swarm", risk=85, is_cross_module_task=True)
    assert set(GATES) <= selected
    invokers = build_mainchain_capability_invokers()
    context: dict[str, Any] = {
        "task_id": "t-1737",
        "task_statement": "mainchain gate wiring",
        "workspace_root": str(tmp_path),
        "verify_commands": ["python -c 'print(1)'"],
        "intent_pass": True,
        "risk_score": 10,
        "target_files": ["a.py"],
        "impact_map": {"a.py": ["b.py"]},
        "acceptance_criteria": ["ok"],
        "deliverables": ["a.py"],
        "steps": ["s1"],
        "handoff_readiness": True,
        # forecast_gate is an escalate_only executor; the caller must trigger it.
        "executor_flags": {"forecast_gate": True},
    }
    for gate in GATES:
        receipt = invokers[gate](context)
        assert receipt["skipped"] is False, (gate, receipt.get("skip_reason"))
        assert receipt["invoked"] is True
        assert receipt.get("skip_reason") != "not_implemented_mainchain_v1"
        assert receipt["physical_callable"].startswith("capability_executor_registry:"), gate


def test_forecast_gate_without_escalation_trigger_is_policy_skip_not_not_implemented(
    tmp_path,
) -> None:
    receipt = build_mainchain_capability_invokers()["forecast_gate"]({
        "task_id": "t",
        "workspace_root": str(tmp_path),
    })
    assert receipt["skipped"] is True
    assert receipt["skip_reason"] == "SKIPPED_POLICY_NOT_TRIGGERED"
