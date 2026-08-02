from __future__ import annotations

from typing import Any

from nexus.contracts.claim_evidence_read_model import build_claim_evidence_read_model
from nexus.contracts.optimization_report import ClaimClass
from nexus.evidence.claim_boundary import ClaimBoundary
from nexus.research.epistemic_profile.contracts import (
    EpistemicIntegrityStatus,
    EpistemicProfileInput,
    EpistemicReceiptExtension,
    EpistemicVerificationResult,
)

ALLOWED_COMPLETION_STATUSES = {
    "NOT_APPLICABLE",
    "PASS",
    "SUCCESS",
    "FAIL",
    "FAILED",
    "ERROR",
    "RETURN",
    "BLOCKED",
}

FAILING_COMPLETION_STATUSES = {
    "FAIL",
    "FAILED",
    "ERROR",
    "RETURN",
    "BLOCKED",
}


def validate_epistemic_profile_input(inp: EpistemicProfileInput) -> tuple[str, ...]:
    blockers: list[str] = []

    if not getattr(inp, "task_id", None) or not str(inp.task_id).strip():
        blockers.append("EP_MISSING_TASK_ID")
    if not getattr(inp, "attempt_id", None) or not str(inp.attempt_id).strip():
        blockers.append("EP_MISSING_ATTEMPT_ID")
    if not getattr(inp, "profile_id", None) or not str(inp.profile_id).strip():
        blockers.append("EP_MISSING_PROFILE_ID")
    if not getattr(inp, "run_id", None) or not str(inp.run_id).strip():
        blockers.append("EP_MISSING_RUN_ID")
    if not getattr(inp, "masked_brief_ref", None) or not str(inp.masked_brief_ref).strip():
        blockers.append("EP_MISSING_MASKED_BRIEF_REF")
    if not getattr(inp, "position_commitment_ref", None) or not str(inp.position_commitment_ref).strip():
        blockers.append("EP_MISSING_POSITION_COMMITMENT_REF")

    comp_status = str(getattr(inp, "completion_status", "") or "NOT_APPLICABLE").upper()
    if comp_status not in ALLOWED_COMPLETION_STATUSES:
        blockers.append("EP_INVALID_COMPLETION_STATUS")
    elif comp_status in FAILING_COMPLETION_STATUSES:
        blockers.append("EP_COMPLETION_STATUS_FAILED")
    elif comp_status in {"PASS", "SUCCESS"} and not (getattr(inp, "completion_envelope_ref", None) and str(inp.completion_envelope_ref).strip()):
        blockers.append("EP_MISSING_COMPLETION_ENVELOPE_REF")

    records = getattr(inp, "records", None)
    if not records:
        blockers.append("EP_MISSING_EVIDENCE_RECORDS")
    else:
        for rec in records:
            if getattr(rec, "run_id", None) != getattr(inp, "run_id", None):
                blockers.append("EP_CROSS_RUN_RECORD")

            claim_id = getattr(rec, "claim_id", None)
            if not claim_id or not str(claim_id).strip():
                blockers.append("EP_MISSING_CLAIM_ID")

            art = getattr(rec, "artifact", None)
            if not art or not getattr(art, "artifact_id", None) or not str(art.artifact_id).strip():
                blockers.append("EP_MISSING_ARTIFACT_REF")

            if not art or not getattr(art, "relative_ref", None) or not str(art.relative_ref).strip():
                blockers.append("EP_MISSING_ARTIFACT_RELATIVE_REF")

            ext_ref = getattr(rec, "extraction_ref", None)
            if not ext_ref or not str(ext_ref).strip():
                blockers.append("EP_MISSING_EXTRACTION_REF")

            asm_ref = getattr(rec, "assessment_ref", None)
            if not asm_ref or not str(asm_ref).strip():
                blockers.append("EP_MISSING_ASSESSMENT_REF")

            if getattr(rec, "evidence_hash_status", "PASS") != "PASS":
                blockers.append("EP_EVIDENCE_HASH_STATUS_FAILED")
            if getattr(rec, "evidence_seal_status", "PASS") != "PASS":
                blockers.append("EP_EVIDENCE_SEAL_STATUS_FAILED")

            rec_blockers = getattr(rec, "blockers", ())
            if rec_blockers:
                blockers.extend(rec_blockers)

    return tuple(dict.fromkeys(blockers))


def build_epistemic_claim_evidence_read_model(inp: EpistemicProfileInput) -> dict[str, Any]:
    input_blockers = validate_epistemic_profile_input(inp)
    generic_records = []
    evidence_bundle_refs = []
    receipt_refs = []

    records = getattr(inp, "records", ()) or ()
    for rec in records:
        rec_blockers = list(input_blockers)
        if getattr(rec, "evidence_hash_status", "PASS") != "PASS":
            rec_blockers.append("evidence_hash_verification_failed")
        if getattr(rec, "evidence_seal_status", "PASS") != "PASS":
            rec_blockers.append("evidence_seal_verification_failed")
        rec_custom_blockers = getattr(rec, "blockers", ())
        if rec_custom_blockers:
            rec_blockers.extend(rec_custom_blockers)

        ext_ref = getattr(rec, "extraction_ref", "") or ""
        asm_ref = getattr(rec, "assessment_ref", "") or ""
        if ext_ref:
            evidence_bundle_refs.append(ext_ref)
        if asm_ref:
            evidence_bundle_refs.append(asm_ref)

        rec_receipts = getattr(rec, "receipt_refs", ()) or ()
        receipt_refs.extend(rec_receipts)

        claim_id = getattr(rec, "claim_id", "unknown")
        generic_records.append({
            "name": f"epistemic_record_{claim_id}",
            "delivery_status": "PASS" if not rec_blockers else "RETURN",
            "trust_status": "PASS" if not rec_blockers else "FAIL",
            "provider_token_cleanliness": "not_applicable",
            "evidence_refs": [r for r in [ext_ref, asm_ref] if r],
            "receipt_refs": list(rec_receipts),
            "evidence_seal_status": getattr(rec, "evidence_seal_status", "PASS"),
            "evidence_hash_status": getattr(rec, "evidence_hash_status", "PASS"),
            "blockers": rec_blockers,
        })

    model_dict = build_claim_evidence_read_model(
        claim_class=ClaimClass.INTERNAL_DIAGNOSTIC,
        records=generic_records,
        evidence_bundle_refs=evidence_bundle_refs,
        receipt_refs=receipt_refs,
        sealed_evidence_required=False,
        completion_status=getattr(inp, "completion_status", "NOT_APPLICABLE"),
        completion_envelope_ref=getattr(inp, "completion_envelope_ref", ""),
    )

    if input_blockers:
        existing_blockers = model_dict.get("blockers", [])
        combined = tuple(dict.fromkeys(list(input_blockers) + list(existing_blockers)))
        model_dict["blockers"] = list(combined)
        model_dict["status"] = "RETURN"

    return model_dict


def build_epistemic_verification_result(inp: EpistemicProfileInput) -> EpistemicVerificationResult:
    input_blockers = validate_epistemic_profile_input(inp)
    read_model = build_epistemic_claim_evidence_read_model(inp)
    read_model_blockers = tuple(read_model.get("blockers", []))

    all_blockers = tuple(dict.fromkeys(input_blockers + read_model_blockers))

    evidence_refs = []
    receipt_refs = []
    records = getattr(inp, "records", ()) or ()
    for rec in records:
        ext_ref = getattr(rec, "extraction_ref", "")
        asm_ref = getattr(rec, "assessment_ref", "")
        if ext_ref:
            evidence_refs.append(ext_ref)
        if asm_ref:
            evidence_refs.append(asm_ref)
        receipt_refs.extend(getattr(rec, "receipt_refs", ()) or ())

    status = EpistemicIntegrityStatus.PASS if not all_blockers else EpistemicIntegrityStatus.RETURN

    return EpistemicVerificationResult(
        status=status,
        records_checked=len(records),
        evidence_refs=tuple(dict.fromkeys(evidence_refs)),
        receipt_refs=tuple(dict.fromkeys(receipt_refs)),
        blockers=all_blockers,
        claim_evidence_read_model=read_model,
    )


def build_epistemic_receipt_extension(inp: EpistemicProfileInput) -> EpistemicReceiptExtension:
    ver_res = build_epistemic_verification_result(inp)
    boundary = ClaimBoundary()

    return EpistemicReceiptExtension(
        profile_id=getattr(inp, "profile_id", ""),
        run_id=getattr(inp, "run_id", ""),
        records_checked=ver_res.records_checked,
        evidence_refs=ver_res.evidence_refs,
        receipt_refs=ver_res.receipt_refs,
        blockers=ver_res.blockers,
        claim_boundary=boundary,
    )
