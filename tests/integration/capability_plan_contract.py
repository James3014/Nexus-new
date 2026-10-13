"""Shared contract helpers for the capability-phase e2e tests (#1924).

Since #514 (c46780d32) ``NEXUS_SKIP_*`` no longer changes the planner's selection: the planner
decides, and ExecutorControls runs exactly what it planned. These helpers pin that contract.
"""

from __future__ import annotations

from typing import Any

import pytest

from nexus.core import executor_controls
from nexus.core.belief_contracts import (
    CapabilityReceipt,  # pyright: ignore[reportAttributeAccessIssue]
)
from nexus.core.capability_selector import CapabilityConstraints, CapabilitySelector
from nexus.core.capability_signal_set import CapabilitySignalSet


def plan_for(sig: CapabilitySignalSet) -> Any:
    return CapabilitySelector(project_root="/tmp").select_capabilities(
        sig, CapabilityConstraints(project_root="/tmp")
    )


def executed_names(plan: Any, monkeypatch: pytest.MonkeyPatch, project_root: str) -> list[str]:
    """Run the plan through ExecutorControls with recording executors; return who executed."""
    called: list[str] = []

    def _get_executor(name: str) -> Any:
        def _run(p: Any, task_desc: str) -> CapabilityReceipt:
            called.append(name)
            return CapabilityReceipt(
                capability_name=name,
                selected=True,
                invoked=True,
                evidence_id=f"ev_{name}",
                gate_passed=True,
                outcome={"semantic_status": "SUCCEEDED"},
                skill_receipts=[],
                telemetries={},
                timestamp="2026-10-13T00:00:00+00:00",
            )

        return _run

    monkeypatch.setattr(executor_controls, "get_executor", _get_executor)
    receipts = executor_controls.ExecutorControls(project_root=project_root).execute_plan(
        plan, "task"
    )
    names = [r.capability_name for r in receipts]
    assert set(called) <= set(plan.required_capabilities), (
        "executed a capability the planner did not select"
    )
    assert set(names) <= set(plan.required_capabilities)
    return sorted(names)


def assert_planner_selection(
    sig: CapabilitySignalSet,
    expected: frozenset[str],
    *,
    absent: tuple[str, ...] = (),
    monkeypatch: pytest.MonkeyPatch,
    project_root: str,
) -> None:
    """The plan is exactly the planner's selection, and that selection is what runs."""
    plan = plan_for(sig)
    assert frozenset(plan.required_capabilities) == expected
    for cap in absent:
        assert cap not in plan.required_capabilities, f"{cap} is not planned for this task"
    ran = executed_names(plan, monkeypatch, project_root)
    assert ran, "the planned capabilities must run"
    assert not set(ran) & set(absent)


def assert_skip_env_is_inert(
    sig: CapabilitySignalSet,
    skip_env: str,
    *,
    monkeypatch: pytest.MonkeyPatch,
    project_root: str,
) -> None:
    """NEXUS_SKIP_<CAP>=1 changes neither the planned set nor what runs (#514, c46780d32)."""
    monkeypatch.delenv(skip_env, raising=False)
    baseline = plan_for(sig)
    baseline_ran = executed_names(baseline, monkeypatch, project_root)
    monkeypatch.setenv(skip_env, "1")
    skipped = plan_for(sig)
    assert skipped.required_capabilities == baseline.required_capabilities
    assert skipped.phases == baseline.phases
    assert executed_names(skipped, monkeypatch, project_root) == baseline_ran
