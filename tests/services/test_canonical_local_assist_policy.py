from __future__ import annotations

import pytest

from nexus.services.canonical_local_assist_policy import (
    build_canonical_policy_receipt,
    normalize_local_assist_policy,
)


def _task() -> dict[str, object]:
    return {
        "task_id": "m6-b-001",
        "workspace_revision": "rev-1",
        "task_statement": "implement a bounded bug fix in one file",
        "task_type": "bugfix",
        "route": {"route_features": {"risk_score": 20, "adjusted_root_cause_confidence": 0.9}},
    }


def test_disabled_policy_preserves_existing_runtime_behavior() -> None:
    receipt = build_canonical_policy_receipt(policy="disabled", task=_task())
    assert receipt["policy"] == "disabled"
    assert receipt["canonical_policy"] == "disabled"
    assert receipt["automatic_dispatch"] is False
    assert receipt["runtime_behavior_changed"] is False


def test_planner_policy_is_shadow_alias_with_recommendation() -> None:
    receipt = build_canonical_policy_receipt(policy="planner", task=_task())
    assert receipt["policy"] == "planner"
    assert receipt["canonical_policy"] == "shadow"
    assert receipt["legacy_policy_alias"] == "planner"
    assert receipt["migration_warning"]
    assert receipt["planner_recommendation"]["action"] == "candidate"
    assert receipt["recommendation_visible_before_dispatch"] is True
    assert receipt["automatic_dispatch"] is False
    assert receipt["runtime_behavior_changed"] is False
    assert receipt["route_truth_source"] == "CapabilityPlanner"


def test_explicit_policy_is_advisor_alias() -> None:
    receipt = build_canonical_policy_receipt(policy="explicit", task=_task())
    assert receipt["policy"] == "explicit"
    assert receipt["canonical_policy"] == "advisor"
    assert receipt["legacy_policy_alias"] == "explicit"
    assert receipt["available_actions"] == ["skip", "advisor", "candidate", "verified-subtask"]
    assert receipt["automatic_dispatch"] is False
    assert receipt["runtime_behavior_changed"] is True


def test_shadow_and_advisor_canonical_modes() -> None:
    shadow = build_canonical_policy_receipt(policy="shadow", task=_task())
    assert shadow["canonical_policy"] == "shadow"
    assert shadow["runtime_behavior_changed"] is False
    advisor = build_canonical_policy_receipt(policy="advisor", task=_task())
    assert advisor["canonical_policy"] == "advisor"
    assert advisor["runtime_behavior_changed"] is True


def test_unknown_policy_fails_closed() -> None:
    with pytest.raises(ValueError, match="invalid_local_assist_policy"):
        build_canonical_policy_receipt(policy="unknown", task=_task())
    with pytest.raises(ValueError, match="invalid_local_assist_policy"):
        normalize_local_assist_policy("unknown")
