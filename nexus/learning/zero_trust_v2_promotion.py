from __future__ import annotations

from typing import Any, Mapping

from nexus.learning.zero_trust_v2_sandbox import validate_sandbox_attestation
from nexus.learning.zero_trust_v2_signing_secret import NONPRODUCTION_DEFAULT_SECRETS

READY_FOR_MANUAL_APPLY = "READY_FOR_MANUAL_APPLY"
BLOCKED = "BLOCKED"
DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"


def _get_path(row: Mapping[str, Any], *path: str) -> Any:
    value: Any = row
    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def zero_trust_v2_signature_reasons(
    row: Mapping[str, Any], *, signing_secret: str | None
) -> list[str]:
    """Non-production marker and attestation-signature re-check, shared with the evidence
    accumulation report (#3303). An empty list means the row's signature earns credit."""
    if not signing_secret:
        return ["sandbox_signature_not_verified"]
    if signing_secret in NONPRODUCTION_DEFAULT_SECRETS or row.get("nonproduction_secret") is True:
        return ["nonproduction_signing_secret"]
    attestation = row.get("sandbox_attestation")
    try:
        verdict = validate_sandbox_attestation(
            attestation if isinstance(attestation, Mapping) else {},
            signing_secret=signing_secret,
        )
    except (TypeError, ValueError):
        # A malformed signature (non-ASCII text, say) is one bad row, not a failed report.
        verdict = {"status": "INVALID", "sandbox_mode": None}
    if verdict["status"] != "PASS" or verdict["sandbox_mode"] == "mocked_non_promotion":
        return ["sandbox_signature_invalid"]
    return []


def evaluate_zero_trust_v2_promotion_candidate(
    row: Mapping[str, Any], *, min_v2_evidence_count: int = 3, signing_secret: str | None = None
) -> dict[str, Any]:
    """``signing_secret`` re-verifies the sandbox attestation signature here, where it is
    consumed for credit (#3249); without it, or with a source-default secret, nothing earns credit."""
    capability_id = str(row.get("capability_id") or "")
    skill_id = str(row.get("skill_id") or "")
    reasons: list[str] = []
    security_contract_version = str(row.get("security_contract_version") or "")
    promotion_credit_source = str(row.get("promotion_credit_source") or "")
    v2_evidence_count = int(row.get("v2_evidence_count") or 0)
    v2_trust_mismatch_count = int(row.get("v2_trust_mismatch_count") or 0)

    if security_contract_version != "v2":
        return {
            "schema": "nexus.zero_trust_v2.promotion_candidate.v1",
            "status": DIAGNOSTIC_ONLY,
            "capability_id": capability_id,
            "skill_id": skill_id,
            "reasons": ["security_contract_not_v2"],
            "promotion_credit_source": promotion_credit_source or "none",
            "v2_evidence_count": v2_evidence_count,
            "v2_trust_mismatch_count": v2_trust_mismatch_count,
            "manual_apply_required": False,
        }

    if promotion_credit_source != "v2_only":
        reasons.append("promotion_credit_source_not_v2_only")
    if v2_evidence_count < min_v2_evidence_count:
        reasons.append("insufficient_v2_evidence")
    if v2_trust_mismatch_count != 0:
        reasons.append("v2_trust_mismatch_nonzero")
    if int(row.get("negative_control_blocked_count") or 0) < 1:
        reasons.append("missing_negative_control_block")
    if row.get("receipt_provenance") != "runtime_signed":
        reasons.append("missing_runtime_signed_receipt")
    if not row.get("receipt_signature"):
        reasons.append("missing_receipt_signature")
    if _get_path(row, "sandbox_attestation", "status") != "PASS":
        reasons.append("sandbox_attestation_not_pass")
    reasons.extend(zero_trust_v2_signature_reasons(row, signing_secret=signing_secret))
    if _get_path(row, "baseline_sandwich", "baseline_delta_status") != "CLEAN":
        reasons.append("baseline_not_clean")
    if _get_path(row, "cleanup_attestation", "teardown_status") != "PASS":
        reasons.append("cleanup_not_pass")

    status = BLOCKED if reasons else READY_FOR_MANUAL_APPLY
    return {
        "schema": "nexus.zero_trust_v2.promotion_candidate.v1",
        "status": status,
        "capability_id": capability_id,
        "skill_id": skill_id,
        "reasons": sorted(set(reasons)),
        "promotion_credit_source": promotion_credit_source,
        "v2_evidence_count": v2_evidence_count,
        "v2_trust_mismatch_count": v2_trust_mismatch_count,
        "manual_apply_required": status == READY_FOR_MANUAL_APPLY,
    }
