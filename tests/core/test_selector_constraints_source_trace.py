from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.capability_constraints import CapabilityConstraints
from nexus.core.capability_registry import CapabilityRegistry
from nexus.core.capability_selector import CapabilitySelector
from nexus.core.capability_signal_set import CapabilitySignalSet


def _signal() -> CapabilitySignalSet:
    return CapabilitySignalSet(
        task_id="constraints_source_trace_probe",
        task_desc="Regular coding task",
        risk_level="NORMAL",
        impact_complexity=1.0,
        belief_confidence=0.9,
        skills_triggered=[],
        tenant_id="tenant_constraints_source_trace",
    )


def _constraints(project_root: Path, palace_constraints: dict) -> CapabilityConstraints:
    palace = MagicMock()
    palace.verify_context.return_value = {"status": "ALLOWED"}
    palace.get_skill_constraints.return_value = palace_constraints
    return CapabilityConstraints(str(project_root), mem_palace=palace)


def _plan(project_root: Path, palace_constraints: dict) -> CapabilityExecutionPlan:
    selector = CapabilitySelector(CapabilityRegistry(), project_root=str(project_root))
    plan = selector.select_capabilities(_signal(), _constraints(project_root, palace_constraints))
    assert isinstance(plan, CapabilityExecutionPlan), plan
    return plan


def test_plan_trace_carries_unavailable_constraints_source(tmp_path: Path) -> None:
    plan = _plan(
        tmp_path,
        {
            "forbid": [],
            "require": [],
            "prefer": [],
            "constraints_source": "unavailable",
            "constraints_unavailable_reason": "table_read_failed",
        },
    )

    assert plan.constraints["constraints_source"] == "unavailable"
    assert plan.constraints["constraints_unavailable_reason"] == "table_read_failed"


def test_plan_trace_defaults_to_ok_source_and_keeps_routing(tmp_path: Path) -> None:
    legacy = _plan(tmp_path, {"forbid": [], "require": [], "prefer": []})
    unavailable = _plan(
        tmp_path,
        {
            "forbid": [],
            "require": [],
            "prefer": [],
            "constraints_source": "unavailable",
            "constraints_unavailable_reason": "table_read_failed",
        },
    )

    assert legacy.constraints["constraints_source"] == "ok"
    assert legacy.constraints["constraints_unavailable_reason"] == ""
    assert unavailable.required_capabilities == legacy.required_capabilities
    assert unavailable.phases == legacy.phases
