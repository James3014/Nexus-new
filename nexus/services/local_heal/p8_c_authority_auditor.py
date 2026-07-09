from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P8CAuthorityAuditResult:
    audit_version: str = "1.0"
    receipt_present: bool = False
    candidate_like_output_available: bool = False
    p2_hash_truth_required: bool = True
    p2_anchor_truth_required: bool = True
    p4_verifier_required: bool = True
    p4_claim_gate_required: bool = True
    p2_apply_executed: bool = False
    p4_verifier_executed: bool = False
    patch_apply_invoked: bool = False
    solved_claim: bool = False
    claim_eligible: bool = False
    public_claim_allowed: bool = False
    production_ready: bool = False
    authority_audit_passed: bool = False
    rollback_required: bool = False
    blocked_reasons: list[str] = field(default_factory=list)


def audit_authority(receipt: dict[str, Any]) -> P8CAuthorityAuditResult:
    blocked = []
    rollback = []
    p2h = receipt.get("p2_hash_truth_required", True)
    p2a = receipt.get("p2_anchor_truth_required", True)
    p4v = receipt.get("p4_verifier_required", True)
    p4cg = receipt.get("p4_claim_gate_required", True)
    pa = receipt.get("patch_apply_invoked", False)
    sc = receipt.get("solved_claim", False)
    ce = receipt.get("claim_eligible", False)
    pc = receipt.get("public_claim_allowed", False)
    pr = receipt.get("production_ready", False)

    if not p2h: blocked.append("p2_hash_truth_missing")
    if not p2a: blocked.append("p2_anchor_truth_missing")
    if not p4v: blocked.append("p4_verifier_missing")
    if not p4cg: blocked.append("p4_claim_gate_missing")
    if pa: rollback.append("patch_apply_invoked")
    if sc: rollback.append("solved_claim")
    if ce: rollback.append("claim_eligible")
    if pc: rollback.append("public_claim_allowed")
    if pr: rollback.append("production_ready")

    return P8CAuthorityAuditResult(
        receipt_present=True,
        p2_hash_truth_required=p2h, p2_anchor_truth_required=p2a,
        p4_verifier_required=p4v, p4_claim_gate_required=p4cg,
        patch_apply_invoked=pa, solved_claim=sc, claim_eligible=ce,
        public_claim_allowed=pc, production_ready=pr,
        authority_audit_passed=len(blocked) == 0 and len(rollback) == 0,
        rollback_required=len(rollback) > 0,
        blocked_reasons=blocked + rollback,
    )
