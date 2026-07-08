from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ClaimDeliveryDecision:
    claim_gate_passed: bool
    delivery_gate_passed: bool
    reasons: list[str] = field(default_factory=list)
    required_refs: list[str] = field(default_factory=list)


class ClaimDeliveryGate:
    """Strict proof-backed local-heal claim/delivery validator."""

    def validate(self, payload: dict[str, Any]) -> ClaimDeliveryDecision:
        reasons: list[str] = []
        refs = [str(item).strip() for item in payload.get("artifact_refs", []) if str(item).strip()]
        verifier_status = str(payload.get("verifier_status") or "").lower()
        if verifier_status not in {"pass", "passed", "success"}:
            reasons.append("verifier_not_passed")
        if not str(payload.get("verifier_artifact") or "").strip():
            reasons.append("missing_verifier_artifact")
        if not str(payload.get("source_hash") or "").strip():
            reasons.append("missing_source_hash")
        # P2-C: Hash mismatch blocks claim
        candidate_hash_matches_applied = payload.get("candidate_hash_matches_applied", True)
        if not candidate_hash_matches_applied:
            reasons.append("candidate_hash_mismatch")
        # P2-E: Target file presence check
        candidate_target_file = str(payload.get("candidate_target_file", "") or "")
        source_hash_present = bool(str(payload.get("source_hash", "") or "").strip())
        if source_hash_present and not candidate_target_file.strip():
            reasons.append("missing_candidate_target_file")
        if not payload.get("patch_applied"):
            reasons.append("patch_not_applied")
        if not refs:
            reasons.append("missing_artifact_refs")
        if payload.get("owner_gated") and not payload.get("owner_approved"):
            reasons.append("owner_gated_requires_approval")
        if payload.get("unsupported"):
            reasons.append("unsupported_task")
        passed = not reasons
        return ClaimDeliveryDecision(
            claim_gate_passed=passed,
            delivery_gate_passed=passed,
            reasons=reasons,
            required_refs=[
                str(payload.get("verifier_artifact") or ""),
                str(payload.get("source_hash") or ""),
                *refs,
            ],
        )


def validate_context_claim_delivery(
    ctx: Any,
    gate: ClaimDeliveryGate | None = None,
    *,
    candidate_hash_matches_applied: bool | None = None,
) -> dict[str, Any]:
    op = ctx.op if hasattr(ctx, "op") else ctx
    failure_reason = str(getattr(op, "failure_reason", "") or "")
    # P2-D: Resolve hash match — explicit param > op field > route_context > True (backward compat)
    if candidate_hash_matches_applied is None:
        candidate_hash_matches_applied = getattr(op, "selected_candidate_hash_matches_applied", None)
    if candidate_hash_matches_applied is None:
        route_ctx = getattr(op, "route_context", {}) or {}
        candidate_hash_matches_applied = route_ctx.get("candidate_hash_matches_applied", True)
    if candidate_hash_matches_applied is None:
        candidate_hash_matches_applied = True
    decision = (gate or ClaimDeliveryGate()).validate(
        {
            "verifier_status": "pass" if getattr(op, "solve_eligible", False) and not failure_reason else "fail",
            "verifier_artifact": "verification_report.txt" if str(getattr(op, "evaluation_report", "") or "") else "",
            "source_hash": str(getattr(op, "source_hash", "") or ""),
            "patch_applied": bool(getattr(op, "final_patch", "")),
            "artifact_refs": ["patch.diff"] if getattr(op, "final_patch", "") else [],
            "owner_gated": "owner" in failure_reason.lower(),
            "owner_approved": bool(getattr(op, "owner_approved", False)),
            "unsupported": "unsupported" in failure_reason.lower(),
            # P2-C/D: Hash match from explicit param or op field
            "candidate_hash_matches_applied": candidate_hash_matches_applied,
            # P2-E: Target file presence
            "candidate_target_file": str(getattr(op, "candidate_target_file", "") or ""),
        }
    )
    out = {
        "schema": "nexus.local_heal.claim_delivery_gate.v1",
        "claim_gate_passed": decision.claim_gate_passed,
        "delivery_gate_passed": decision.delivery_gate_passed,
        "failure_reasons": decision.reasons,
        "evidence_refs": [item for item in decision.required_refs if item],
        "receipt_only_claim_impossible": True,
        "public_claim_allowed": False,
        "production_ready": False,
        "internal_only": True,
    }
    setattr(op, "_claim_delivery_gate", out)
    return out
