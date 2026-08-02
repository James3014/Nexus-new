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


def validate_epistemic_profile_input(inp: EpistemicProfileInput) -> tuple[str, ...]:
    blockers: list[str] = []

    if not inp.task_id or not inp.task_id.strip():
        blockers.append("EP_MISSING_TASK_ID")
    if not inp.attempt_id or not inp.attempt_id.strip():
        blockers.append("EP_MISSING_ATTEMPT_ID")
    if not inp.profile_id or not inp.profile_id.strip():
        blockers.append("EP_MISSING_PROFILE_ID")
    if not inp.run_id or not inp.run_id.strip():
        blockers.append("EP_MISSING_RUN_ID")
    if not inp.masked_brief_ref or not inp.masked_brief_ref.strip():
        blockers.append("EP_MISSING_MASKED_BRIEF_REF")
    if not inp.position_commitment_ref or not inp.position_commitment_ref.strip():
        blockers.append("EP_MISSING_POSITION_COMMITMENT_REF")

    comp_status = str(inp.completion_status or "NOT_APPLICABLE").upper()
    if comp_status in {"FAIL", "FAILED", "ERROR"}:
        blockers.append("EP_COMPLETION_STATUS_FAILED")
    if comp_status in {"PASS", "SUCCESS"} and not (inp.completion_envelope_ref and inp.completion_envelope_ref.strip()):
        blockers.append("EP_MISSING_COMPLETION_ENVELOPE_REF")

    if not inp.records:
        blockers.append("EP_MISSING_EVIDENCE_RECORDS")

    for rec in inp.records:
        if rec.run_id != inp.run_id:
            blockers.append("EP_CROSS_RUN_RECORD")
        if not rec.artifact or not rec.artifact.artifact_id or not rec.artifact.artifact_id.strip():
            blockers.append("EP_MISSING_ARTIFACT_REF")
        if not rec.extraction_ref or not rec.extraction_ref.strip():
            blockers.append("EP_MISSING_EXTRACTION_REF")
        if not rec.assessment_ref or not rec.assessment_ref.strip():
            blockers.append("EP_MISSING_ASSESSMENT_REF")
        if rec.evidence_hash_status != "PASS":
            blockers.append("EP_EVIDENCE_HASH_STATUS_FAILED")
        if rec.evidence_seal_status != "PASS":
            blockers.append("EP_EVIDENCE_SEAL_STATUS_FAILED")
        if rec.blockers:
            blockers.extend(rec.blockers)

    return tuple(dict.fromkeys(blockers))


def build_epistemic_claim_evidence_read_model(inp: EpistemicProfileInput) -> dict[str, Any]:
    generic_records = []
    evidence_bundle_refs = []
    receipt_refs = []

    for rec in inp.records:
        rec_blockers = []
        if rec.evidence_hash_status != "PASS":
            rec_blockers.append("evidence_hash_verification_failed")
        if rec.evidence_seal_status != "PASS":
            rec_blockers.append("evidence_seal_verification_failed")
        if rec.blockers:
            rec_blockers.extend(rec.blockers)

        evidence_bundle_refs.extend([rec.extraction_ref, rec.assessment_ref])
        receipt_refs.extend(rec.receipt_refs)

        generic_records.append({
            "name": f"epistemic_record_{rec.claim_id}",
            "delivery_status": "PASS" if not rec_blockers else "RETURN",
            "trust_status": "PASS" if not rec_blockers else "FAIL",
            "provider_token_cleanliness": "not_applicable",
            "evidence_refs": [rec.extraction_ref, rec.assessment_ref],
            "receipt_refs": list(rec.receipt_refs),
            "evidence_seal_status": rec.evidence_seal_status,
            "evidence_hash_status": rec.evidence_hash_status,
            "blockers": rec_blockers,
        })

    model_dict = build_claim_evidence_read_model(
        claim_class=ClaimClass.INTERNAL_DIAGNOSTIC,
        records=generic_records,
        evidence_bundle_refs=evidence_bundle_refs,
        receipt_refs=receipt_refs,
        sealed_evidence_required=False,
        completion_status=inp.completion_status,
        completion_envelope_ref=inp.completion_envelope_ref,
    )
    return model_dict


def build_epistemic_verification_result(inp: EpistemicProfileInput) -> EpistemicVerificationResult:
    input_blockers = validate_epistemic_profile_input(inp)
    read_model = build_epistemic_claim_evidence_read_model(inp)
    read_model_blockers = tuple(read_model.get("blockers", []))

    all_blockers = tuple(dict.fromkeys(input_blockers + read_model_blockers))

    evidence_refs = []
    receipt_refs = []
    for rec in inp.records:
        evidence_refs.extend([rec.extraction_ref, rec.assessment_ref])
        receipt_refs.extend(rec.receipt_refs)

    status = EpistemicIntegrityStatus.PASS if not all_blockers else EpistemicIntegrityStatus.RETURN

    return EpistemicVerificationResult(
        status=status,
        records_checked=len(inp.records),
        evidence_refs=tuple(dict.fromkeys(evidence_refs)),
        receipt_refs=tuple(dict.fromkeys(receipt_refs)),
        blockers=all_blockers,
        claim_evidence_read_model=read_model,
    )


def build_epistemic_receipt_extension(inp: EpistemicProfileInput) -> EpistemicReceiptExtension:
    ver_res = build_epistemic_verification_result(inp)
    boundary = ClaimBoundary()

    return EpistemicReceiptExtension(
        profile_id=inp.profile_id,
        run_id=inp.run_id,
        records_checked=len(inp.records),
        evidence_refs=ver_res.evidence_refs,
        receipt_refs=ver_res.receipt_refs,
        blockers=ver_res.blockers,
        claim_boundary=boundary,
    )
