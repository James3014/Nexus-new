"""Fail-closed calibration of shadow recommendation evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


CALIBRATION_SCHEMA = "nexus.local_assist.calibration.v1"
THRESHOLDS = {
    "recommendation_coverage_min": 1.0,
    "unsafe_recommendation_rate_max": 0.0,
    "false_positive_assist_rate_max": 0.10,
    "exact_action_agreement_min": 0.75,
    "unexplained_disagreement_count_max": 0,
}


def calibrate_shadow_policy(metrics: Mapping[str, Any]) -> dict[str, Any]:
    observed = dict(metrics)
    failures: list[str] = []
    try:
        if float(observed.get("recommendation_coverage", 0.0)) < THRESHOLDS["recommendation_coverage_min"]:
            failures.append("recommendation_coverage")
        if float(observed.get("unsafe_recommendation_rate", 1.0)) > THRESHOLDS["unsafe_recommendation_rate_max"]:
            failures.append("unsafe_recommendation_rate")
        if float(observed.get("false_positive_assist_rate", 1.0)) > THRESHOLDS["false_positive_assist_rate_max"]:
            failures.append("false_positive_assist_rate")
        if float(observed.get("exact_action_agreement", 0.0)) < THRESHOLDS["exact_action_agreement_min"]:
            failures.append("exact_action_agreement")
        if int(observed.get("unexplained_disagreement_count", 0)) > THRESHOLDS["unexplained_disagreement_count_max"]:
            failures.append("unexplained_disagreement_count")
    except (TypeError, ValueError):
        failures.append("invalid_calibration_metrics")
    return {
        "schema": CALIBRATION_SCHEMA,
        "status": "CALIBRATED" if not failures else "BLOCKED",
        "policy_source": "shadow_evidence",
        "thresholds": dict(THRESHOLDS),
        "observed_metrics": observed,
        "failed_thresholds": list(dict.fromkeys(failures)),
        "route_authority_unchanged": True,
        "route_truth_source": "CapabilityPlanner",
        "automatic_dispatch_enabled": False,
        "shadow_only": True,
    }


def write_calibration_evidence(path: str | Path, result: Mapping[str, Any]) -> Path:
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(dict(result), indent=2, sort_keys=True), encoding="utf-8")
    return destination
