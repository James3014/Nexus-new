from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P7ArmorReceipt:
    receipt_version: str = "1.0"
    receipt_id: str = ""
    source_trace_id: str = ""
    p3_status: str = ""
    p6_status: str = ""
    p3_candidate_trace_ref: str = ""
    p6_handoff_trace_ref: str = ""
    p2_hash_truth_required: bool = True
    p2_anchor_truth_required: bool = True
    p4_verifier_required: bool = True
    p4_claim_gate_required: bool = True
    p5_metadata_required: bool = True
    provider_invoked: bool = False
    network_invoked: bool = False
    api_key_used: bool = False
    local_model_invoked_by_p7: bool = False
    patch_apply_invoked: bool = False
    runtime_behavior_changed: bool = False
    solved_claim: bool = False
    claim_eligible: bool = False
    public_claim_allowed: bool = False
    production_ready: bool = False
    invariant_passed: bool = True
    receipt_complete: bool = True
    blocked_reasons: list[str] = field(default_factory=list)


def build_armor_receipts(trace_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for r in trace_rows:
        blocked = []
        if r.get("p3_real_provider_invoked"): blocked.append("provider_invoked")
        if r.get("p3_network_invoked"): blocked.append("network_invoked")
        if r.get("p3_api_key_used"): blocked.append("api_key_used")
        if r.get("patch_apply_invoked"): blocked.append("patch_apply_invoked")
        if r.get("runtime_behavior_changed"): blocked.append("runtime_behavior_changed")
        if r.get("solved_claim"): blocked.append("solved_claim")
        if r.get("claim_eligible"): blocked.append("claim_eligible")
        if r.get("public_claim_allowed"): blocked.append("public_claim_allowed")
        if r.get("production_ready"): blocked.append("production_ready")
        if not r.get("p2_hash_truth_required", True): blocked.append("p2_hash_truth_missing")
        if not r.get("p4_verifier_required", True): blocked.append("p4_verifier_missing")
        if not r.get("p4_claim_gate_required", True): blocked.append("p4_claim_gate_missing")
        if not r.get("p6_advisory_only", True): blocked.append("p6_not_advisory")

        inv_pass = len(blocked) == 0
        receipt = P7ArmorReceipt(
            receipt_id=f"R-{r.get('trace_id', 'X')}",
            source_trace_id=r.get("trace_id", ""),
            p3_status=r.get("p3_closed_status", ""),
            p6_status=r.get("p6_closed_status", ""),
            p2_hash_truth_required=r.get("p2_hash_truth_required", True),
            p2_anchor_truth_required=r.get("p2_anchor_truth_required", True),
            p4_verifier_required=r.get("p4_verifier_required", True),
            p4_claim_gate_required=r.get("p4_claim_gate_required", True),
            provider_invoked=r.get("p3_real_provider_invoked", False),
            network_invoked=r.get("p3_network_invoked", False),
            api_key_used=r.get("p3_api_key_used", False),
            patch_apply_invoked=r.get("patch_apply_invoked", False),
            runtime_behavior_changed=r.get("runtime_behavior_changed", False),
            solved_claim=r.get("solved_claim", False),
            claim_eligible=r.get("claim_eligible", False),
            public_claim_allowed=r.get("public_claim_allowed", False),
            production_ready=r.get("production_ready", False),
            invariant_passed=inv_pass,
            receipt_complete=inv_pass,
            blocked_reasons=blocked,
        )
        results.append({
            "receipt_version": receipt.receipt_version, "receipt_id": receipt.receipt_id,
            "source_trace_id": receipt.source_trace_id, "p3_status": receipt.p3_status,
            "p6_status": receipt.p6_status, "p2_hash_truth_required": receipt.p2_hash_truth_required,
            "p2_anchor_truth_required": receipt.p2_anchor_truth_required,
            "p4_verifier_required": receipt.p4_verifier_required,
            "p4_claim_gate_required": receipt.p4_claim_gate_required,
            "p5_metadata_required": receipt.p5_metadata_required,
            "provider_invoked": receipt.provider_invoked, "network_invoked": receipt.network_invoked,
            "api_key_used": receipt.api_key_used, "local_model_invoked_by_p7": receipt.local_model_invoked_by_p7,
            "patch_apply_invoked": receipt.patch_apply_invoked,
            "runtime_behavior_changed": receipt.runtime_behavior_changed,
            "solved_claim": receipt.solved_claim, "claim_eligible": receipt.claim_eligible,
            "public_claim_allowed": receipt.public_claim_allowed,
            "production_ready": receipt.production_ready,
            "invariant_passed": receipt.invariant_passed,
            "receipt_complete": receipt.receipt_complete,
            "blocked_reasons": receipt.blocked_reasons,
        })
    return results
