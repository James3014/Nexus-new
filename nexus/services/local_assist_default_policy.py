"""Evidence-backed Local Assist policy recommendation without runtime promotion."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from nexus.services.local_assist_value_matrix import EVALUATION_ARMS


_ACTIONS = ("skip", "advisor", "candidate", "verified-subtask")


def _score(rows: list[Mapping[str, Any]]) -> tuple[float, float]:
    valid = [row for row in rows if bool(row.get("infrastructure_valid", True))]
    verified = sum(bool(row.get("verified", False)) for row in valid)
    rate = verified / len(valid) if valid else 0.0
    cost = sum(float(row.get("cost", 0.0) or 0.0) for row in valid)
    return rate, cost


def decide_default_policy(matrix: Mapping[str, Any]) -> dict[str, Any]:
    matrix = dict(matrix or {})
    base = {
        "schema": "nexus.local_assist.default_policy.v1",
        "runtime_defaults_promoted": False,
        "route_authority_unchanged": True,
        "public_claim_allowed": False,
        "production_ready": False,
        "internal_only": True,
        "default_by_action": {action: "" for action in _ACTIONS},
    }
    if matrix.get("value_measured") is not True:
        return {**base, "status": "INSUFFICIENT_EVIDENCE", "reason": "value_matrix_not_measured"}
    rows_by_arm = matrix.get("rows", {})
    if not isinstance(rows_by_arm, Mapping):
        return {**base, "status": "INSUFFICIENT_EVIDENCE", "reason": "matrix_rows_missing"}
    defaults: dict[str, str] = {}
    for action in _ACTIONS:
        candidates: list[tuple[float, float, str]] = []
        for arm in EVALUATION_ARMS:
            rows = [
                row
                for row in (rows_by_arm.get(arm, []) or [])
                if isinstance(row, Mapping) and row.get("recommended_action") == action
            ]
            if rows:
                rate, cost = _score(rows)
                candidates.append((rate, cost, arm))
        if candidates:
            defaults[action] = sorted(candidates, key=lambda item: (-item[0], item[1], item[2]))[0][2]
    if any(not defaults.get(action) for action in _ACTIONS):
        return {**base, "status": "INSUFFICIENT_EVIDENCE", "reason": "action_family_evidence_missing"}
    global_rates = {
        arm: float((matrix.get("arms", {}).get(arm, {}) or {}).get("verified_solve_rate", 0.0))
        for arm in EVALUATION_ARMS
    }
    cloud_first_superior = global_rates.get("G0_online_agent_bare", 0.0) > global_rates.get("G3_nexus_full_local_assist", 0.0)
    local_only_sufficient = global_rates.get("L1_local_only_armor", 0.0) >= global_rates.get("G3_nexus_full_local_assist", 0.0)
    return {
        **base,
        "status": "DECIDED",
        "reason": "bounded_comparative_evidence",
        "default_by_action": defaults,
        "advisor_default_where": [action for action in _ACTIONS if defaults[action] == "G2_nexus_local_advisor"],
        "candidate_default_where": [action for action in _ACTIONS if action == "candidate"],
        "verified_subtask_default_where": [action for action in _ACTIONS if action == "verified-subtask"],
        "skip_where": [action for action in _ACTIONS if action == "skip"],
        "cloud_first_superior": cloud_first_superior,
        "local_only_sufficient": local_only_sufficient,
        "evidence_matrix_schema": matrix.get("schema", ""),
    }


def write_default_policy(path: str | Path, policy: Mapping[str, Any]) -> Path:
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(dict(policy), indent=2, sort_keys=True), encoding="utf-8")
    return destination
