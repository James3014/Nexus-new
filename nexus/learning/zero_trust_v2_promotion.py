from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Mapping

from nexus.learning.zero_trust_v2_receipts import verify_runtime_signed_receipt
from nexus.learning.zero_trust_v2_sandbox import validate_sandbox_attestation
from nexus.learning.zero_trust_v2_signing_secret import NONPRODUCTION_DEFAULT_SECRETS

READY_FOR_MANUAL_APPLY = "READY_FOR_MANUAL_APPLY"
BLOCKED = "BLOCKED"
DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"

# What a signed receipt proves (#3355); the kind is part of the signed inputs.
V2_EVIDENCE_KIND = "v2_evidence"
NEGATIVE_CONTROL_BLOCK_KIND = "negative_control_block"
NO_CREDIT_KIND = "no_credit"
CANDIDATE_ARM_TYPES = frozenset({"candidate_skill_v2", "shadow_candidate_v2"})
NEGATIVE_CONTROL_ARM_TYPE = "wrong_or_quarantined_skill_v2"


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
    secret_reasons = _secret_reasons(row, signing_secret=signing_secret)
    if secret_reasons:
        return secret_reasons
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


def _secret_reasons(row: Mapping[str, Any], *, signing_secret: str | None) -> list[str]:
    if not signing_secret:
        return ["sandbox_signature_not_verified"]
    if signing_secret in NONPRODUCTION_DEFAULT_SECRETS or row.get("nonproduction_secret") is True:
        return ["nonproduction_signing_secret"]
    return []


def zero_trust_v2_candidate_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("capability_id") or ""),
        str(row.get("source_skill_id") or row.get("skill_id") or ""),
    )


_IDENTITY_FIELDS = ("capability_id", "source_skill_id", "row_id", "arm_id")


def verified_zero_trust_v2_proof(
    row: Mapping[str, Any], *, signing_secret: str | None
) -> tuple[dict[str, Any] | None, list[str]]:
    """Verify one row's runtime-signed receipt and bind its signed inputs to the row (#3355).

    Returns ``(proof, [])`` with the candidate key, the signed evidence kind and the
    signature that identifies the proof, or ``(None, reasons)``."""
    reasons = _secret_reasons(row, signing_secret=signing_secret)
    if reasons:
        return None, reasons
    try:
        receipt_ok = verify_runtime_signed_receipt(row, secret=str(signing_secret))
    except (TypeError, ValueError):
        receipt_ok = False
    if not receipt_ok:
        return None, ["receipt_not_verified"]
    inputs = row["receipt_signature_inputs"]
    # A validly signed receipt without the identity fields is one bad row, not a failed report
    # (#3372).
    if any(field not in inputs for field in _IDENTITY_FIELDS):
        return None, ["receipt_identity_missing"]
    arm_type = str(row.get("arm_type") or "")
    bound = (
        str(inputs.get("row_id") or "") == str(row.get("row_id") or "")
        and str(inputs.get("arm_id") or "") == arm_type
        and str(inputs.get("capability_id") or "") == str(row.get("capability_id") or "")
        and str(inputs.get("skill_id") or "") == str(row.get("skill_id") or "")
        and str(inputs.get("source_skill_id") or "") == zero_trust_v2_candidate_key(row)[1]
    )
    if not bound:
        return None, ["receipt_inputs_not_bound_to_row"]
    kind = str(inputs.get("evidence_kind") or NO_CREDIT_KIND)
    if kind == V2_EVIDENCE_KIND:
        if arm_type not in CANDIDATE_ARM_TYPES:
            return None, ["receipt_kind_not_valid_for_arm"]
        attestation_reasons = zero_trust_v2_signature_reasons(row, signing_secret=signing_secret)
        if attestation_reasons:
            return None, attestation_reasons
        attested_artifact = _get_path(row, "sandbox_attestation", "artifact_hash")
        if attested_artifact != inputs.get("artifact_hash"):
            return None, ["receipt_artifact_not_bound_to_attestation"]
    elif kind == NEGATIVE_CONTROL_BLOCK_KIND:
        if arm_type != NEGATIVE_CONTROL_ARM_TYPE:
            return None, ["receipt_kind_not_valid_for_arm"]
    elif kind != NO_CREDIT_KIND:
        return None, ["receipt_kind_unknown"]
    return {
        "key": (str(inputs["capability_id"]), str(inputs["source_skill_id"])),
        # One problem's evidence, whatever round or signature it came from (#3362).
        "identity": (
            str(inputs["capability_id"]),
            str(inputs["source_skill_id"]),
            str(inputs.get("row_id") or ""),
            str(inputs.get("arm_id") or ""),
        ),
        "kind": kind,
        "proof_id": str(row.get("receipt_signature")),
        "row_id": row.get("row_id"),
    }, []


def _new_counts() -> dict[str, Any]:
    return {
        "v2_evidence_count": 0,
        "v2_trust_mismatch_count": 0,
        "negative_control_blocked_count": 0,
        "row_refs": [],
        "rejected_rows": 0,
        "rejected_row_refs": [],
        "duplicate_proof_count": 0,
        "duplicate_identity_count": 0,
        "duplicate_identity_row_refs": [],
        "unsigned_count_mismatch_row_refs": [],
    }


def _mismatch_value(row: Mapping[str, Any]) -> int | None:
    """The unsigned ``v2_trust_mismatch_count`` as a non-negative int (absent is 0), or None
    when it is out of range or not an integer (#3362)."""
    value = row.get("v2_trust_mismatch_count")
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def derive_zero_trust_v2_signed_counts(
    rows: Iterable[Mapping[str, Any]], *, signing_secret: str | None
) -> dict[tuple[str, str], dict[str, Any]]:
    """Per candidate, the v2 evidence and negative-control counts derived only from verified,
    de-duplicated signed receipts: each proof counts once, whatever the row columns say (#3355),
    and each signed identity (capability, source skill, row, arm) counts once across rounds and
    signatures; the merged repeats are listed, not dropped silently (#3362). Shared by the
    accumulation report and the promotion evaluator."""
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    seen: set[str] = set()
    seen_identities: set[tuple[str, str, str, str]] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        proof, _reasons = verified_zero_trust_v2_proof(row, signing_secret=signing_secret)
        mismatch = _mismatch_value(row)
        if proof is None or mismatch is None:
            item = by_key.setdefault(zero_trust_v2_candidate_key(row), _new_counts())
            item["rejected_rows"] += 1
            item["rejected_row_refs"].append(row.get("row_id"))
            continue
        item = by_key.setdefault(proof["key"], _new_counts())
        # Not signed; it can only block, and the producer always writes 0. Out-of-range values
        # reject the row above, so a negative value cannot cancel another row's mismatch; a
        # repeat still adds its mismatch, so merging repeats can only block more (#3362).
        item["v2_trust_mismatch_count"] += mismatch
        if proof["proof_id"] in seen:
            item["duplicate_proof_count"] += 1
            continue
        seen.add(proof["proof_id"])
        if proof["identity"] in seen_identities:
            item["duplicate_identity_count"] += 1
            item["duplicate_identity_row_refs"].append(proof["row_id"])
            continue
        seen_identities.add(proof["identity"])
        item["row_refs"].append(proof["row_id"])
        credited_v2 = 1 if proof["kind"] == V2_EVIDENCE_KIND else 0
        if proof["kind"] == NEGATIVE_CONTROL_BLOCK_KIND:
            item["negative_control_blocked_count"] += 1
            if int(row.get("negative_control_blocked_count") or 0) != 1:
                item["unsigned_count_mismatch_row_refs"].append(proof["row_id"])
        item["v2_evidence_count"] += credited_v2
        if int(row.get("v2_evidence_count") or 0) != credited_v2:
            item["unsigned_count_mismatch_row_refs"].append(proof["row_id"])
    return by_key


def evaluate_zero_trust_v2_promotion_candidate(
    row: Mapping[str, Any], *, min_v2_evidence_count: int = 3, signing_secret: str | None = None
) -> dict[str, Any]:
    """``signing_secret`` re-verifies the sandbox attestation signature here, where it is
    consumed for credit (#3249); without it, or with a source-default secret, nothing earns credit.
    Evidence and negative-control counts come from the verified signed receipts of the row and
    its ``signed_proofs`` (#3355), never from the row's own count columns."""
    capability_id = str(row.get("capability_id") or "")
    skill_id = str(row.get("skill_id") or "")
    reasons: list[str] = []
    security_contract_version = str(row.get("security_contract_version") or "")
    promotion_credit_source = str(row.get("promotion_credit_source") or "")
    own_mismatch = _mismatch_value(row)
    v2_trust_mismatch_count = own_mismatch if own_mismatch is not None else -1
    secret_reasons = _secret_reasons(row, signing_secret=signing_secret)
    proofs = [
        row,
        *[item for item in (row.get("signed_proofs") or []) if isinstance(item, Mapping)],
    ]
    counts = (
        derive_zero_trust_v2_signed_counts(proofs, signing_secret=signing_secret).get(
            zero_trust_v2_candidate_key(row), _new_counts()
        )
        if not secret_reasons
        else _new_counts()
    )
    v2_evidence_count = int(counts["v2_evidence_count"])

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
    # Without a usable secret nothing is counted and the secret reason blocks the row; the count
    # reasons then describe the row's own (unverified) claim, never credit (#3355).
    claimed = row if secret_reasons else counts
    if int(claimed.get("v2_evidence_count") or 0) < min_v2_evidence_count:
        reasons.append("insufficient_v2_evidence")
    if v2_trust_mismatch_count != 0 or int(counts["v2_trust_mismatch_count"]) != 0:
        reasons.append("v2_trust_mismatch_nonzero")
    if int(claimed.get("negative_control_blocked_count") or 0) < 1:
        reasons.append("missing_negative_control_block")
    if row.get("receipt_provenance") != "runtime_signed":
        reasons.append("missing_runtime_signed_receipt")
    if not row.get("receipt_signature"):
        reasons.append("missing_receipt_signature")
    elif not secret_reasons:
        own_proof, proof_reasons = verified_zero_trust_v2_proof(row, signing_secret=signing_secret)
        if any(reason.startswith("receipt_") for reason in proof_reasons):
            reasons.append("receipt_not_verified")
        # The row's own receipt must itself be v2 evidence; attached proofs cannot stand in
        # (#3362). A row whose proof failed is already blocked by the reasons above.
        if own_proof is not None and own_proof["kind"] != V2_EVIDENCE_KIND:
            reasons.append("row_receipt_not_v2_evidence")
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
