from __future__ import annotations

import json

from nexus.engine.local_assist_shadow_runtime import (
    SHADOW_RECEIPT_SCHEMA,
    DEFAULT_SHADOW_TASKS,
    record_shadow_decision,
    run_shadow_task_set,
)


def test_shadow_decision_records_independent_agent_choice(tmp_path) -> None:
    receipt = record_shadow_decision(
        task_id="m3-b-001",
        workspace_revision="rev-1",
        task_desc="localize an uncertain failure",
        task_type="localization",
        route={"route_features": {"risk_score": 40, "adjusted_root_cause_confidence": 0.35}},
        agent_actual_choice="skip",
        override_reason="agent judged local evidence sufficient",
        receipt_path=tmp_path / "shadow.json",
    )
    assert receipt["schema"] == SHADOW_RECEIPT_SCHEMA
    assert receipt["task_id"] == "m3-b-001"
    assert receipt["planner_recommendation"]["action"] == "advisor"
    assert receipt["agent_actual_choice"] == "skip"
    assert receipt["recommendation_match"] is False
    assert receipt["recommendation_overridden"] is True
    assert receipt["assist_result"]["status"] == "not_invoked"
    assert receipt["local_assist_invoked"] is False
    assert json.loads((tmp_path / "shadow.json").read_text()) == receipt


def test_matching_choice_has_no_override_and_preserves_lineage(tmp_path) -> None:
    receipt = record_shadow_decision(
        task_id="m3-b-002",
        workspace_revision="rev-2",
        task_desc="implement a bounded bug fix in one file",
        task_type="bugfix",
        route={"route_features": {"risk_score": 20, "adjusted_root_cause_confidence": 0.9}},
        agent_actual_choice="candidate",
        receipt_path=tmp_path / "shadow.json",
    )
    assert receipt["planner_recommendation"]["action"] == "candidate"
    assert receipt["recommendation_match"] is True
    assert receipt["recommendation_overridden"] is False
    assert receipt["override_reason"] == ""
    assert receipt["local_assist_task_id"] == "m3-b-002"
    assert receipt["workspace_revision"] == "rev-2"


def test_shadow_dataset_has_three_tasks_per_action_and_required_shapes() -> None:
    assert len(DEFAULT_SHADOW_TASKS) >= 12
    assert {task["category"] for task in DEFAULT_SHADOW_TASKS} >= {
        "test-only",
        "source-localization",
        "bounded-bug-fix",
        "verifier-sensitive",
        "no-change",
        "insufficient-context",
    }
    metrics = run_shadow_task_set()
    assert metrics["task_count"] >= 12
    assert metrics["recommendation_coverage"] == 1.0
    assert metrics["action_counts"] == {
        "skip": 3,
        "advisor": 3,
        "candidate": 3,
        "verified-subtask": 3,
    }
    assert metrics["unsafe_recommendation_rate"] == 0.0
    assert metrics["local_assist_invocations"] == 0
