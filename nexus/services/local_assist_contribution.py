"""Fail-closed causal contribution attribution."""

from __future__ import annotations

from typing import Any, Mapping


CONTRIBUTION_SCHEMA = "nexus.local_assist.contribution.v1"
_CONTRIBUTION_TYPES = {"localization", "candidate", "verification", "rejection", "retry"}


def evaluate_contribution(
    *,
    receipt: Mapping[str, Any],
    consumption: Mapping[str, Any],
    causal_evidence: Mapping[str, Any],
    contribution_type: str,
    counterfactual_available: bool = False,
    confidence: float = 0.0,
) -> dict[str, Any]:
    if contribution_type not in _CONTRIBUTION_TYPES:
        raise ValueError("invalid_contribution_type")
    receipt = dict(receipt or {})
    consumption = dict(consumption or {})
    causal = dict(causal_evidence or {})
    refs = [str(ref) for ref in (causal.get("evidence_refs", []) or []) if str(ref)]
    receipt_present = bool(receipt.get("task_id") and receipt.get("output_delivered"))
    receipt_consumed = bool(consumption.get("receipt_identities"))
    output_used = bool(consumption.get("output_used", False))
    if not receipt_present:
        reason = "receipt_missing_or_not_delivered"
    elif not receipt_consumed:
        reason = "receipt_only_insufficient"
    elif not output_used:
        reason = "consumption_only_insufficient"
    elif not refs:
        reason = "causal_evidence_incomplete"
    else:
        valid_causal_link = False
        if contribution_type == "candidate":
            accepted = {str(item) for item in (causal.get("accepted_content_hashes", []) or []) if str(item)}
            generated = {str(item) for item in (receipt.get("candidate_hashes", []) or []) if str(item)}
            valid_causal_link = bool(causal.get("candidate_content_adopted")) and bool(accepted & generated)
        elif contribution_type == "localization":
            valid_causal_link = bool(causal.get("target_selected_from_assist"))
        elif contribution_type == "verification":
            valid_causal_link = bool(causal.get("verifier_feedback_changed_final"))
        elif contribution_type == "rejection":
            valid_causal_link = bool(causal.get("prevented_invalid_modification"))
        elif contribution_type == "retry":
            valid_causal_link = bool(causal.get("retry_triggered_by_assist"))
        reason = "" if valid_causal_link else "causal_evidence_incomplete"
    contributed = reason == ""
    accepted_hashes = [str(item) for item in (causal.get("accepted_content_hashes", []) or []) if str(item)]
    bounded_confidence = max(0.0, min(1.0, float(confidence))) if contributed else 0.0
    return {
        "schema": CONTRIBUTION_SCHEMA,
        "outcome_contributed": contributed,
        "contribution_type": contribution_type if contributed else "",
        "evidence_refs": refs,
        "accepted_content_hashes": accepted_hashes if contributed else [],
        "counterfactual_available": bool(counterfactual_available),
        "confidence": bounded_confidence,
        "reason": reason,
        "value_measured": False,
        "claim_boundary": {
            "receipt_present": receipt_present,
            "output_consumed": receipt_consumed and output_used,
            "outcome_contributed": contributed,
            "value_measured": False,
            "production_ready": False,
            "public_claim_allowed": False,
            "internal_only": True,
        },
    }
