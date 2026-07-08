from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CommitteeActivationInput:
    execution_topology: str = ""
    p3_route_status: str = ""
    hard_case_escalation_recommended: bool = False
    difficulty: str = ""
    cloud_candidate_generated: bool = False
    stage4_local_retry_success: bool = False
    stage3_verifier_passed: bool = False
    local_committee_enabled: bool = False
    proposer_specs: list[dict[str, str]] = field(default_factory=list)
    judge_model: str = ""
    claim_gate_already_passed: bool = False


# Enable conditions — ALL must be true
ENABLE_CONDITIONS = [
    ("execution_topology == cloud_with_local_assist",
     lambda i: i.execution_topology == "cloud_with_local_assist"),
    ("p3_route_status == shadow_stage5_escalation_recommended",
     lambda i: i.p3_route_status == "shadow_stage5_escalation_recommended"),
    ("hard_case_escalation_recommended == true",
     lambda i: i.hard_case_escalation_recommended),
    ("difficulty == hard",
     lambda i: i.difficulty == "hard"),
    ("local_retry_failed",
     lambda i: not i.stage4_local_retry_success),
    ("local_committee_enabled == true",
     lambda i: i.local_committee_enabled),
    ("proposer_specs >= 2",
     lambda i: len(i.proposer_specs) >= 2),
    ("judge_model present",
     lambda i: bool(i.judge_model)),
    ("P4 env guard enabled",
     lambda i: os.environ.get("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", "0") == "1"),
]

# Disable conditions — ANY triggers block
DISABLE_CONDITIONS = [
    ("difficulty easy/medium",
     lambda i: i.difficulty in ("easy", "medium")),
    ("P2 claim gate already passed",
     lambda i: i.claim_gate_already_passed),
    ("local_committee_enabled false",
     lambda i: not i.local_committee_enabled),
    ("proposer_specs missing",
     lambda i: len(i.proposer_specs) < 2),
    ("judge_model missing",
     lambda i: not bool(i.judge_model)),
    ("P4 env guard off",
     lambda i: os.environ.get("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", "0") != "1"),
    ("local_only topology",
     lambda i: i.execution_topology == "local_only"),
]


def evaluate_committee_activation(inputs: CommitteeActivationInput) -> dict:
    """Evaluate all enable/disable conditions. Return gate decision dict.

    Enable conditions checked first. ALL must pass.
    Then disable conditions checked. ANY blocks.
    """
    # Track which conditions were checked
    enable_results = {}
    disable_results = {}

    # Check enable conditions
    all_enable_passed = True
    for name, check in ENABLE_CONDITIONS:
        passed = check(inputs)
        enable_results[name] = passed
        if not passed:
            all_enable_passed = False

    # Check disable conditions
    any_disable_hit = False
    blocked_reason = ""
    for name, check in DISABLE_CONDITIONS:
        hit = check(inputs)
        disable_results[name] = hit
        if hit:
            any_disable_hit = True
            if not blocked_reason:
                blocked_reason = name

    # Decision
    invocation_allowed = all_enable_passed and not any_disable_hit

    if not all_enable_passed:
        failed_enables = [name for name, passed in enable_results.items() if not passed]
        blocked_reason = f"enable_conditions_failed: {', '.join(failed_enables[:3])}"
    elif any_disable_hit:
        pass  # blocked_reason already set

    return {
        "gate_evaluated": True,
        "invocation_allowed": invocation_allowed,
        "blocked_reason": blocked_reason if not invocation_allowed else "",
        "activation_inputs": {
            "execution_topology": inputs.execution_topology,
            "p3_route_status": inputs.p3_route_status,
            "hard_case_escalation_recommended": inputs.hard_case_escalation_recommended,
            "difficulty": inputs.difficulty,
            "stage4_local_retry_success": inputs.stage4_local_retry_success,
            "local_committee_enabled": inputs.local_committee_enabled,
            "proposer_specs_count": len(inputs.proposer_specs),
            "judge_model_present": bool(inputs.judge_model),
            "enable_results": enable_results,
            "disable_results": disable_results,
        },
    }
