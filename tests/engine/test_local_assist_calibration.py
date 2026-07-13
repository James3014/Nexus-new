from __future__ import annotations

import json

from nexus.engine.local_assist_calibration import (
    CALIBRATION_SCHEMA,
    calibrate_shadow_policy,
    write_calibration_evidence,
)
from nexus.engine.local_assist_shadow_runtime import run_shadow_task_set


def test_shadow_policy_calibrates_when_all_thresholds_pass(tmp_path) -> None:
    metrics = run_shadow_task_set()
    result = calibrate_shadow_policy(metrics)
    assert result["schema"] == CALIBRATION_SCHEMA
    assert result["status"] == "CALIBRATED"
    assert result["route_authority_unchanged"] is True
    assert result["policy_source"] == "shadow_evidence"
    path = write_calibration_evidence(tmp_path / "calibration.json", result)
    assert json.loads(path.read_text()) == result


def test_unsafe_recommendation_blocks_calibration() -> None:
    result = calibrate_shadow_policy(
        {
            "task_count": 12,
            "recommendation_coverage": 1.0,
            "exact_action_agreement": 0.9,
            "safe_disagreement_rate": 1.0,
            "unsafe_recommendation_rate": 0.01,
            "false_positive_assist_rate": 0.0,
            "false_negative_assist_rate": 0.0,
            "unexplained_disagreement_count": 0,
        }
    )
    assert result["status"] == "BLOCKED"
    assert "unsafe_recommendation_rate" in result["failed_thresholds"]


def test_weak_agreement_blocks_calibration() -> None:
    result = calibrate_shadow_policy(
        {
            "task_count": 12,
            "recommendation_coverage": 1.0,
            "exact_action_agreement": 0.74,
            "safe_disagreement_rate": 1.0,
            "unsafe_recommendation_rate": 0.0,
            "false_positive_assist_rate": 0.0,
            "false_negative_assist_rate": 0.0,
            "unexplained_disagreement_count": 0,
        }
    )
    assert result["status"] == "BLOCKED"
    assert "exact_action_agreement" in result["failed_thresholds"]


def test_unexplained_disagreement_blocks_calibration() -> None:
    result = calibrate_shadow_policy(
        {
            "task_count": 12,
            "recommendation_coverage": 1.0,
            "exact_action_agreement": 0.9,
            "safe_disagreement_rate": 1.0,
            "unsafe_recommendation_rate": 0.0,
            "false_positive_assist_rate": 0.0,
            "false_negative_assist_rate": 0.0,
            "unexplained_disagreement_count": 1,
        }
    )
    assert result["status"] == "BLOCKED"
    assert "unexplained_disagreement_count" in result["failed_thresholds"]
