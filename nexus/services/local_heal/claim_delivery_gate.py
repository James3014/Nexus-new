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


def validate_context_claim_delivery(ctx: Any, gate: ClaimDeliveryGate | None = None) -> dict[str, Any]:
    op = ctx.op if hasattr(ctx, "op") else ctx
    failure_reason = str(getattr(op, "failure_reason", "") or "")
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
