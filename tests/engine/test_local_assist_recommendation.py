from __future__ import annotations

import json

from nexus.engine.capability_planner import CapabilityPlanner
from nexus.engine.local_assist_recommendation import (
    RECOMMENDATION_SCHEMA,
    build_local_assist_recommendation,
    write_local_assist_recommendation_receipt,
)


def _plan(*, task_desc: str, task_type: str, route_features: dict | None = None) -> dict:
    plan = CapabilityPlanner().plan(
        task_desc=task_desc,
        task_type=task_type,
        route={"pillar_signals": {}, "route_features": route_features or {}},
        budget={"max_cost": 100},
    )
    return plan.signal_snapshot


def test_simple_low_risk_task_recommends_skip() -> None:
    snapshot = _plan(
        task_desc="inspect one file for a typo; no implementation is requested",
        task_type="audit",
        route_features={"risk_score": 5, "adjusted_root_cause_confidence": 0.95},
    )
    recommendation = snapshot["local_assist_recommendation"]
    assert recommendation["schema"] == RECOMMENDATION_SCHEMA
    assert recommendation["recommended"] is True
    assert recommendation["action"] == "skip"


def test_localization_uncertainty_recommends_advisor() -> None:
    snapshot = _plan(
        task_desc="localize an uncertain failure and identify the likely source",
        task_type="localization",
        route_features={"risk_score": 40, "adjusted_root_cause_confidence": 0.35},
    )
    assert snapshot["local_assist_recommendation"]["action"] == "advisor"


def test_bounded_implementation_recommends_candidate() -> None:
    snapshot = _plan(
        task_desc="implement a bounded bug fix in one target file",
        task_type="bugfix",
        route_features={"risk_score": 20, "adjusted_root_cause_confidence": 0.9},
    )
    assert snapshot["local_assist_recommendation"]["action"] == "candidate"


def test_verifier_sensitive_change_recommends_verified_subtask() -> None:
    snapshot = _plan(
        task_desc="make a verifier-sensitive change and run the deterministic verifier",
        task_type="implementation",
        route_features={"risk_score": 45, "adjusted_root_cause_confidence": 0.8},
    )
    assert snapshot["local_assist_recommendation"]["action"] == "verified-subtask"


def test_missing_planner_evidence_fails_closed_to_skip() -> None:
    recommendation = build_local_assist_recommendation(
        task_desc="bounded bug fix",
        task_type="bugfix",
        planner_snapshot={},
    )
    assert recommendation["action"] == "skip"
    assert recommendation["confidence"] == 0.0
    assert "missing_planner_evidence" in recommendation["reason_codes"]


def test_forbidden_mutation_never_becomes_automatic_mutation() -> None:
    snapshot = _plan(
        task_desc="directly mutate the formal workspace without isolation",
        task_type="implementation",
        route_features={"risk_score": 80, "adjusted_root_cause_confidence": 0.7},
    )
    recommendation = snapshot["local_assist_recommendation"]
    assert recommendation["action"] in {"advisor", "skip"}
    assert recommendation["mutation_allowed"] is False
    assert recommendation["shadow_only"] is True


def test_recommendation_preserves_capability_planner_as_route_truth() -> None:
    snapshot = _plan(
        task_desc="bounded bug fix in one file",
        task_type="bugfix",
        route_features={"risk_score": 20, "adjusted_root_cause_confidence": 0.9},
    )
    recommendation = snapshot["local_assist_recommendation"]
    assert recommendation["route_truth_source"] == "CapabilityPlanner"
    assert recommendation["shadow_only"] is True
    assert recommendation["mutation_allowed"] is False


def test_repeated_input_produces_identical_recommendation() -> None:
    kwargs = {
        "task_desc": "bounded bug fix in one file",
        "task_type": "bugfix",
        "planner_snapshot": {
            "planner_version": "capability_planner_v1",
            "route_truth_source": "CapabilityPlanner",
            "risk_score_0_100": 20,
            "risk_band": "low",
            "confidence": 0.9,
            "candidate_factory_ready_estimate": True,
            "candidate_factory_estimated_candidates": 1,
        },
    }
    assert build_local_assist_recommendation(**kwargs) == build_local_assist_recommendation(**kwargs)


def test_recommendation_receipt_is_machine_readable(tmp_path) -> None:
    snapshot = _plan(
        task_desc="bounded bug fix in one file",
        task_type="bugfix",
        route_features={"risk_score": 20, "adjusted_root_cause_confidence": 0.9},
    )
    path = write_local_assist_recommendation_receipt(
        tmp_path / "recommendation.json",
        task_id="m3-a-test",
        workspace_revision="abc123",
        recommendation=snapshot["local_assist_recommendation"],
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["task_id"] == "m3-a-test"
    assert payload["workspace_revision"] == "abc123"
    assert payload["planner_recommendation"]["schema"] == RECOMMENDATION_SCHEMA
