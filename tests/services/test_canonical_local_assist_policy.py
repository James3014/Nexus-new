from __future__ import annotations

import json

import pytest

from nexus.services.canonical_local_assist_policy import build_canonical_policy_receipt


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
    assert receipt["automatic_dispatch"] is False
    assert receipt["runtime_behavior_changed"] is False


def test_planner_policy_exposes_recommendation_without_auto_execution() -> None:
    receipt = build_canonical_policy_receipt(policy="planner", task=_task())
    assert receipt["policy"] == "planner"
    assert receipt["planner_recommendation"]["action"] == "candidate"
    assert receipt["recommendation_visible_before_dispatch"] is True
    assert receipt["automatic_dispatch"] is False
    assert receipt["route_truth_source"] == "CapabilityPlanner"


def test_explicit_policy_preserves_explicit_seam() -> None:
    receipt = build_canonical_policy_receipt(policy="explicit", task=_task())
    assert receipt["policy"] == "explicit"
    assert receipt["available_actions"] == ["skip", "advisor", "candidate", "verified-subtask"]
    assert receipt["automatic_dispatch"] is False


def test_unknown_policy_fails_closed() -> None:
    with pytest.raises(ValueError, match="invalid_local_assist_policy"):
        build_canonical_policy_receipt(policy="unknown", task=_task())
