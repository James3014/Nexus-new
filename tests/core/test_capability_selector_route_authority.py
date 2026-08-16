from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import nexus.core.capability_selector as capability_selector_module
from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.capability_constraints import CapabilityConstraints
from nexus.core.capability_registry import CapabilityRegistry
from nexus.core.capability_selector import CapabilitySelector
from nexus.core.capability_signal_set import CapabilitySignalSet

_POLICY_REL = Path(".nexus") / "memory" / "dynamic_learning_policy.json"


def _write_policy(project_root: Path, payload: dict | str) -> Path:
    path = project_root / _POLICY_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _make_selector(project_root: Path) -> CapabilitySelector:
    return CapabilitySelector(CapabilityRegistry(), project_root=str(project_root))


def _make_constraints(project_root: Path) -> CapabilityConstraints:
    mock_palace = MagicMock()
    mock_palace.verify_context.return_value = {"status": "ALLOWED"}
    mock_palace.get_skill_constraints.return_value = {"forbid": [], "require": [], "prefer": []}
    return CapabilityConstraints(str(project_root), mem_palace=mock_palace)


def _normal_signal(task_id: str = "route_authority_probe") -> CapabilitySignalSet:
    return CapabilitySignalSet(
        task_id=task_id,
        task_desc="Regular coding task",
        risk_level="NORMAL",
        impact_complexity=1.0,
        belief_confidence=0.9,
        skills_triggered=[],
        tenant_id="tenant_route_authority",
    )


def _normal_plan(project_root: Path) -> CapabilityExecutionPlan:
    plan = _make_selector(project_root).select_capabilities(
        _normal_signal(), _make_constraints(project_root)
    )
    assert isinstance(plan, CapabilityExecutionPlan), plan
    return plan


def _baseline_signature(project_root: Path) -> tuple:
    plan = _normal_plan(project_root)
    return (plan.required_capabilities, plan.phases)


def _valid_pass_policy() -> dict:
    return {
        "schema_version": "nexus_dynamic_learning_policy.v1",
        "status": "PASS",
        "promoted_capabilities": ["benchmark_meta_opt"],
        "penalized_capabilities": ["mempalace"],
    }


def test_legacy_promoted_capability_cannot_be_appended(tmp_path: Path) -> None:
    """A PASS legacy policy promoting a registered capability cannot add it to the plan."""
    _write_policy(tmp_path, _valid_pass_policy())
    plan = _normal_plan(tmp_path)
    assert "mempalace" in plan.required_capabilities
    assert "benchmark_meta_opt" not in plan.required_capabilities


def test_legacy_penalized_capability_cannot_be_removed(tmp_path: Path) -> None:
    """A PASS legacy policy penalizing a selected capability cannot remove it from the plan."""
    _write_policy(tmp_path, _valid_pass_policy())
    plan = _normal_plan(tmp_path)
    assert "mempalace" in plan.required_capabilities


def test_missing_policy_leaves_plan_unchanged(tmp_path: Path) -> None:
    assert _normal_plan(tmp_path).required_capabilities == list(_baseline_signature(tmp_path)[0])


def test_malformed_policy_fails_closed(tmp_path: Path) -> None:
    """Malformed policy JSON cannot alter the selector plan or raise."""
    _write_policy(tmp_path, "{not valid json")
    assert _normal_plan(tmp_path).required_capabilities == list(_baseline_signature(tmp_path)[0])


def test_foreign_schema_policy_fails_closed(tmp_path: Path) -> None:
    payload = _valid_pass_policy()
    payload["schema_version"] = "nexus.other.v9"
    _write_policy(tmp_path, payload)
    assert _normal_plan(tmp_path).required_capabilities == list(_baseline_signature(tmp_path)[0])


def test_non_pass_status_policy_fails_closed(tmp_path: Path) -> None:
    payload = _valid_pass_policy()
    payload["status"] = "FAIL"
    _write_policy(tmp_path, payload)
    assert _normal_plan(tmp_path).required_capabilities == list(_baseline_signature(tmp_path)[0])


def test_tampered_policy_cannot_alter_plan(tmp_path: Path) -> None:
    """A valid-schema policy with arbitrary promoted/penalized values leaves the plan identical."""
    payload = _valid_pass_policy()
    payload["promoted_capabilities"] = ["benchmark_meta_opt", "swarm_multi_agent"]
    payload["penalized_capabilities"] = ["mempalace", "codeintel", "belief"]
    _write_policy(tmp_path, payload)
    assert _normal_plan(tmp_path).required_capabilities == list(_baseline_signature(tmp_path)[0])


def test_skip_behavior_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """NEXUS_SKIP_* controls still apply after legacy policy authority removal."""
    monkeypatch.setenv("NEXUS_SKIP_MEMPALACE", "1")
    plan = _normal_plan(tmp_path)
    assert "mempalace" not in plan.required_capabilities


def test_legacy_route_authority_seam_removed() -> None:
    """The legacy dynamic-learning-policy route authority seam is gone from the module."""
    assert not hasattr(capability_selector_module, "_load_dynamic_learning_policy_safe")
