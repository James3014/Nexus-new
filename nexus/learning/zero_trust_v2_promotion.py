from __future__ import annotations

from typing import Any, Mapping


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


def evaluate_zero_trust_v2_promotion_candidate(row: Mapping[str, Any], *, min_v2_evidence_count: int = 3) -> dict[str, Any]:
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
