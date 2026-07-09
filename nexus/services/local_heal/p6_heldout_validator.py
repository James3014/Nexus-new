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
    unknown_quota_as_healthy_violations: int = 0
    constrained_candidate_count_violations: int = 0
    exhausted_local_unavailable_violations: int = 0
    action_permission_consistency_violations: int = 0
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

    # P6-E1: Safety rule checks
    unknown_as_healthy = 0
    constrained_count_violations = 0
    exhausted_unavailable_violations = 0
    action_perm_violations = 0
    invalid_ids = []

    for row in rows:
        qs = row.get("quota_scenario", "")
        action = row.get("expected_degradation_action", "")
        cloud_ok = row.get("expected_cloud_allowed", True)
        local_ok = row.get("expected_local_allowed", True)
        committee_ok = row.get("expected_committee_allowed", True)
        p5_ok = row.get("expected_p5_allowed", True)
        pub_claim = row.get("public_claim_allowed", False)
        cmin = row.get("expected_candidate_count_min", 0)
        cmax = row.get("expected_candidate_count_max", 0)
        verifier = row.get("verifier_required", True)
        claim = row.get("claim_gate_required", True)

        # Rule 1: unknown must not be healthy
        if qs == "unknown" and action == "keep_full_committee":
            unknown_as_healthy += 1
            invalid_ids.append(row.get("case_id", ""))
        if qs == "unknown" and cloud_ok is True:
            unknown_as_healthy += 1
            invalid_ids.append(row.get("case_id", ""))

        # Rule 2: constrained count
        if qs == "constrained" and action == "reduce_candidate_count":
            if cmin < 2:
                constrained_count_violations += 1
                invalid_ids.append(row.get("case_id", ""))
            if cmax < cmin:
                constrained_count_violations += 1
                invalid_ids.append(row.get("case_id", ""))

        # Rule 3: exhausted_local_unavailable
        if qs == "exhausted_local_unavailable" and action not in ("fail_closed", "diagnosis_only"):
            exhausted_unavailable_violations += 1
            invalid_ids.append(row.get("case_id", ""))

        # Rule 4: action/permission consistency
        if action == "keep_full_committee" and committee_ok is False:
            action_perm_violations += 1
            invalid_ids.append(row.get("case_id", ""))
        if action == "reduce_candidate_count" and (committee_ok is False or cmin < 2):
            action_perm_violations += 1
            invalid_ids.append(row.get("case_id", ""))
        if action == "local_only" and cloud_ok is True:
            action_perm_violations += 1
            invalid_ids.append(row.get("case_id", ""))
        if action == "fail_closed" and (cloud_ok is True or local_ok is True or committee_ok is True or p5_ok is True):
            action_perm_violations += 1
            invalid_ids.append(row.get("case_id", ""))
        if action == "diagnosis_only" and pub_claim is True:
            action_perm_violations += 1
            invalid_ids.append(row.get("case_id", ""))

    if unknown_as_healthy > 0:
        blocked.append("unknown_quota_as_healthy")
    if constrained_count_violations > 0:
        blocked.append("constrained_candidate_count_violations")
    if exhausted_unavailable_violations > 0:
        blocked.append("exhausted_local_unavailable_violations")
    if action_perm_violations > 0:
        blocked.append("action_permission_consistency_violations")

    valid = len(blocked) == 0

    return P6HeldoutValidationResult(
        valid=valid,
        case_count=len(rows),
        difficulties_present=sorted(difficulties),
        quota_scenarios_present=sorted(quota_scenarios),
        action_distribution=action_dist,
        missing_required_fields=sorted(missing_fields),
        invalid_cases=list(set(invalid_ids)),
        public_claim_allowed_violations=violations["public_claim_allowed"],
        verifier_required_violations=violations["verifier_required"],
        claim_gate_required_violations=violations["claim_gate_required"],
        production_ready_violations=violations["production_ready"],
        default_runtime_allowed_violations=violations["default_runtime_allowed"],
        unknown_quota_as_healthy_violations=unknown_as_healthy,
        constrained_candidate_count_violations=constrained_count_violations,
        exhausted_local_unavailable_violations=exhausted_unavailable_violations,
        action_permission_consistency_violations=action_perm_violations,
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
