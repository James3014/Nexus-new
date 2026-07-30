from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping

from nexus.contracts.workforce_admission import (
    AdmissionDecision,
    WorkforceAdmissionRequest,
)
from nexus.services.model_workforce_policy import WorkforcePolicyLoader


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


def _admission_role(demand: Mapping[str, Any]) -> str:
    """Map committee semantics to the existing policy role vocabulary."""
    phase = str(demand.get("phase") or "")
    role = str(demand.get("role") or "")
    if phase == "proposal":
        return {
            "primary": "bounded_code_candidate",
            "secondary": "committee_secondary_proposer_only",
        }.get(role, role)
    if phase == "judge":
        return "candidate_ranking"
    if phase == "diagnosis":
        return "compact_diagnosis"
    if phase == "audit":
        return "candidate_ranking"
    if phase == "delegated_retry":
        return "bounded_code_candidate" if role != "secondary" else "committee_secondary_proposer_only"
    return role


def evaluate_committee_member_admission(
    member_demands: list[Mapping[str, Any]],
    *,
    bindings: Mapping[str, Any] | None = None,
    policy_loader: Any | None = None,
) -> dict[str, Any]:
    """Admit every projected member as one fail-closed aggregate.

    This function only evaluates policy. It never invokes a provider and never
    substitutes a missing member. Any malformed/missing binding is a BLOCK.
    """
    bindings = bindings if isinstance(bindings, Mapping) else {}
    loader = policy_loader or WorkforcePolicyLoader()
    records: list[dict[str, Any]] = []
    try:
        snapshot = loader.load()
    except Exception as exc:
        reason = f"policy_load_failed:{type(exc).__name__}:{exc}"
        records = [
            {"member_id": str(item.get("member_id") or ""), "decision": AdmissionDecision.BLOCK.value, "reasons": [reason]}
            for item in member_demands
            if isinstance(item, Mapping)
        ]
        return {
            "schema": "nexus.committee_member_admission.v1",
            "overall_decision": AdmissionDecision.BLOCK.value,
            "zero_call_required": True,
            "records": records,
            "overall_reasons": [reason],
        }

    for index, demand in enumerate(member_demands):
        if not isinstance(demand, Mapping):
            records.append({"member_id": f"malformed:{index}", "decision": AdmissionDecision.BLOCK.value, "reasons": ["member_demand_malformed"]})
            continue
        member_id = str(demand.get("member_id") or "").strip()
        binding = bindings.get(member_id)
        if binding is None:
            binding = {}
        if not isinstance(binding, Mapping):
            records.append({"member_id": member_id, "decision": AdmissionDecision.BLOCK.value, "reasons": ["member_binding_malformed"]})
            continue
        provider = str(binding.get("provider") or demand.get("provider") or "").strip()
        model = str(binding.get("model") or demand.get("model") or "").strip()
        if not member_id or not provider or not model:
            records.append({"member_id": member_id, "decision": AdmissionDecision.BLOCK.value, "reasons": ["member_identity_missing"]})
            continue
        request = WorkforceAdmissionRequest(
            requested_worker_id=(binding.get("worker_id") or binding.get("requested_worker_id")),
            provider=provider,
            model=model,
            role=_admission_role(demand),
            autonomy=str(demand.get("minimum_autonomy") or ""),
            context=str(demand.get("context_class") or ""),
            mutation_requested=bool(demand.get("mutation_intent", False)),
            explicit_experiment_authorization=bool(binding.get("explicit_experiment_authorization", False)),
            route_authorized=demand.get("route_authority") == "CapabilityPlanner",
            provided_controls=tuple(binding.get("controls") or binding.get("provided_controls") or ()),
        )
        try:
            decision = loader.admit(request, snapshot)
            decision_value = decision.decision.value if hasattr(decision.decision, "value") else str(decision.decision)
            reasons = list(decision.decision_reasons)
            record = {
                "member_id": member_id,
                "provider": provider,
                "model": model,
                "requested_role": request.role,
                "decision": decision_value,
                "admitted_role": decision.admitted_role,
                "autonomy_ceiling": decision.autonomy_ceiling,
                "reasons": reasons,
            }
        except Exception as exc:
            record = {
                "member_id": member_id,
                "provider": provider,
                "model": model,
                "decision": AdmissionDecision.BLOCK.value,
                "reasons": [f"admission_failed:{type(exc).__name__}:{exc}"],
            }
        records.append(record)

    values = {str(record.get("decision")) for record in records}
    if AdmissionDecision.BLOCK.value in values or not records:
        overall = AdmissionDecision.BLOCK.value
    elif AdmissionDecision.ESCALATE.value in values:
        overall = AdmissionDecision.ESCALATE.value
    else:
        overall = AdmissionDecision.ALLOW.value
    return {
        "schema": "nexus.committee_member_admission.v1",
        "overall_decision": overall,
        "zero_call_required": overall != AdmissionDecision.ALLOW.value,
        "records": records,
        "overall_reasons": [
            f"{record.get('member_id')}: {reason}"
            for record in records
            for reason in (record.get("reasons") or ())
            if str(record.get("decision")) != AdmissionDecision.ALLOW.value
        ],
    }


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
