from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P6HeldoutValidationResult:
    validator_version: str = "1.0"
    valid: bool = False
    case_count: int = 0
    difficulties_present: list[str] = field(default_factory=list)
    quota_scenarios_present: list[str] = field(default_factory=list)
    action_distribution: dict[str, int] = field(default_factory=dict)
    missing_required_fields: list[str] = field(default_factory=list)
    invalid_cases: list[str] = field(default_factory=list)
    public_claim_allowed_violations: int = 0
    verifier_required_violations: int = 0
    claim_gate_required_violations: int = 0
    production_ready_violations: int = 0
    default_runtime_allowed_violations: int = 0
    blocked_reasons: list[str] = field(default_factory=list)


def validate_heldout_fixture(rows: list[dict[str, Any]]) -> P6HeldoutValidationResult:
    """Validate heldout fixture for consistency and safety."""
    blocked = []

    if len(rows) < 30:
        blocked.append("fewer_than_30_cases")

    # Check required fields
    required_fields = [
        "case_id", "task_difficulty", "quota_scenario", "quota_known",
        "local_available", "expected_degradation_action", "expected_cloud_allowed",
        "expected_local_allowed", "expected_committee_allowed", "expected_p5_allowed",
        "expected_candidate_count_min", "expected_candidate_count_max",
        "verifier_required", "claim_gate_required", "public_claim_allowed",
        "default_runtime_allowed", "production_ready",
    ]

    missing_fields = set()
    for row in rows:
        for field in required_fields:
            if field not in row:
                missing_fields.add(field)
    if missing_fields:
        blocked.append(f"missing_fields: {', '.join(sorted(missing_fields))}")

    # Check difficulty coverage
    difficulties = set()
    quota_scenarios = set()
    action_dist = {}
    violations = {
        "public_claim_allowed": 0,
        "verifier_required": 0,
        "claim_gate_required": 0,
        "production_ready": 0,
        "default_runtime_allowed": 0,
    }

    for row in rows:
        difficulties.add(row.get("task_difficulty", ""))
        quota_scenarios.add(row.get("quota_scenario", ""))
        action = row.get("expected_degradation_action", "")
        action_dist[action] = action_dist.get(action, 0) + 1

        if row.get("public_claim_allowed") is True:
            violations["public_claim_allowed"] += 1
        if row.get("verifier_required") is False:
            violations["verifier_required"] += 1
        if row.get("claim_gate_required") is False:
            violations["claim_gate_required"] += 1
        if row.get("production_ready") is True:
            violations["production_ready"] += 1
        if row.get("default_runtime_allowed") is True:
            violations["default_runtime_allowed"] += 1

    required_difficulties = {"easy", "medium", "hard"}
    required_scenarios = {"healthy", "constrained", "exhausted_local_available", "exhausted_local_unavailable", "unknown"}

    if not required_difficulties.issubset(difficulties):
        blocked.append("missing_difficulty")
    if not required_scenarios.issubset(quota_scenarios):
        blocked.append("missing_quota_scenario")

    for v, count in violations.items():
        if count > 0:
            blocked.append(f"{v}_violations")

    valid = len(blocked) == 0

    return P6HeldoutValidationResult(
        valid=valid,
        case_count=len(rows),
        difficulties_present=sorted(difficulties),
        quota_scenarios_present=sorted(quota_scenarios),
        action_distribution=action_dist,
        missing_required_fields=sorted(missing_fields),
        invalid_cases=[],
        public_claim_allowed_violations=violations["public_claim_allowed"],
        verifier_required_violations=violations["verifier_required"],
        claim_gate_required_violations=violations["claim_gate_required"],
        production_ready_violations=violations["production_ready"],
        default_runtime_allowed_violations=violations["default_runtime_allowed"],
        blocked_reasons=blocked,
    )


def validate_heldout_file(path: str) -> P6HeldoutValidationResult:
    """Validate heldout fixture from JSON file."""
    try:
        with open(path) as f:
            rows = json.load(f)
    except FileNotFoundError:
        return P6HeldoutValidationResult(blocked_reasons=["file_not_found"])
    return validate_heldout_fixture(rows)
