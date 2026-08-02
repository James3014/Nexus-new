from __future__ import annotations

from nexus.contracts.claim_evidence_read_model import CLAIM_EVIDENCE_READ_MODEL_SCHEMA
from nexus.evidence.claim_boundary import ClaimBoundary
from nexus.research.epistemic_profile.adapter import (
    build_epistemic_claim_evidence_read_model,
    build_epistemic_receipt_extension,
    build_epistemic_verification_result,
    validate_epistemic_profile_input,
)
from nexus.research.epistemic_profile.contracts import (
    EpistemicArtifactRef,
    EpistemicDirection,
    EpistemicEvidenceRecord,
    EpistemicIntegrityStatus,
    EpistemicProfileInput,
    EpistemicScopeAlignment,
)


def _make_valid_input() -> EpistemicProfileInput:
    art = EpistemicArtifactRef(
        artifact_id="art_001",
        content_sha256="a" * 64,
        relative_ref="artifacts/art_001.txt",
    )
    rec = EpistemicEvidenceRecord(
        run_id="run_001",
        claim_id="clm_001",
        artifact=art,
        extraction_ref="ext_001",
        assessment_ref="asm_001",
        direction=EpistemicDirection.SUPPORTS,
        scope_alignment=EpistemicScopeAlignment.MATCHED,
        cannot_establish_present=True,
        evidence_hash_status="PASS",
        evidence_seal_status="PASS",
        receipt_refs=("rcp_001",),
    )
    return EpistemicProfileInput(
        task_id="task_001",
        attempt_id="att_001",
        profile_id="prof_001",
        run_id="run_001",
        masked_brief_ref="brief_001",
        position_commitment_ref="pos_001",
        records=(rec,),
        completion_status="PASS",
        completion_envelope_ref="env_001",
    )


def test_positive_internal_diagnostic_profile():
    inp = _make_valid_input()
    blockers = validate_epistemic_profile_input(inp)
    assert len(blockers) == 0

    read_model = build_epistemic_claim_evidence_read_model(inp)
    assert read_model["status"] == "PASS"

    res = build_epistemic_verification_result(inp)
    assert res.status == EpistemicIntegrityStatus.PASS
    assert res.records_checked == 1


def test_uses_existing_claim_evidence_read_model_schema():
    inp = _make_valid_input()
    read_model = build_epistemic_claim_evidence_read_model(inp)
    assert read_model["schema"] == CLAIM_EVIDENCE_READ_MODEL_SCHEMA


def test_missing_artifact_ref_fails_closed():
    inp = _make_valid_input()
    bad_art = EpistemicArtifactRef(
        artifact_id="art_temp",
        content_sha256="a" * 64,
        relative_ref="artifacts/art_001.txt",
    )
    object.__setattr__(bad_art, "artifact_id", "")
    bad_rec = EpistemicEvidenceRecord(
        run_id="run_001",
        claim_id="clm_001",
        artifact=bad_art,
        extraction_ref="ext_001",
        assessment_ref="asm_001",
        cannot_establish_present=True,
    )
    object.__setattr__(inp, "records", (bad_rec,))

    blockers = validate_epistemic_profile_input(inp)
    assert "EP_MISSING_ARTIFACT_REF" in blockers

    res = build_epistemic_verification_result(inp)
    assert res.status == EpistemicIntegrityStatus.RETURN


def test_missing_extraction_ref_fails_closed():
    inp = _make_valid_input()
    bad_rec = EpistemicEvidenceRecord(
        run_id="run_001",
        claim_id="clm_001",
        artifact=EpistemicArtifactRef(
            artifact_id="art_001",
            content_sha256="a" * 64,
            relative_ref="artifacts/art_001.txt",
        ),
        extraction_ref="ext_temp",
        assessment_ref="asm_001",
        cannot_establish_present=True,
    )
    object.__setattr__(bad_rec, "extraction_ref", "")
    object.__setattr__(inp, "records", (bad_rec,))

    blockers = validate_epistemic_profile_input(inp)
    assert "EP_MISSING_EXTRACTION_REF" in blockers


def test_missing_assessment_ref_fails_closed():
    inp = _make_valid_input()
    bad_rec = EpistemicEvidenceRecord(
        run_id="run_001",
        claim_id="clm_001",
        artifact=EpistemicArtifactRef(
            artifact_id="art_001",
            content_sha256="a" * 64,
            relative_ref="artifacts/art_001.txt",
        ),
        extraction_ref="ext_001",
        assessment_ref="asm_temp",
        cannot_establish_present=True,
    )
    object.__setattr__(bad_rec, "assessment_ref", "")
    object.__setattr__(inp, "records", (bad_rec,))

    blockers = validate_epistemic_profile_input(inp)
    assert "EP_MISSING_ASSESSMENT_REF" in blockers


def test_cross_run_record_fails_closed():
    inp = _make_valid_input()
    bad_rec = EpistemicEvidenceRecord(
        run_id="run_OTHER",
        claim_id="clm_001",
        artifact=EpistemicArtifactRef(
            artifact_id="art_001",
            content_sha256="a" * 64,
            relative_ref="artifacts/art_001.txt",
        ),
        extraction_ref="ext_001",
        assessment_ref="asm_001",
        cannot_establish_present=True,
    )
    object.__setattr__(inp, "records", (bad_rec,))

    blockers = validate_epistemic_profile_input(inp)
    assert "EP_CROSS_RUN_RECORD" in blockers


def test_hash_failure_fails_closed():
    inp = _make_valid_input()
    bad_rec = EpistemicEvidenceRecord(
        run_id="run_001",
        claim_id="clm_001",
        artifact=EpistemicArtifactRef(
            artifact_id="art_001",
            content_sha256="a" * 64,
            relative_ref="artifacts/art_001.txt",
        ),
        extraction_ref="ext_001",
        assessment_ref="asm_001",
        cannot_establish_present=True,
        evidence_hash_status="FAIL",
    )
    object.__setattr__(inp, "records", (bad_rec,))

    res = build_epistemic_verification_result(inp)
    assert res.status == EpistemicIntegrityStatus.RETURN
    assert "EP_EVIDENCE_HASH_STATUS_FAILED" in res.blockers


def test_seal_failure_fails_closed():
    inp = _make_valid_input()
    bad_rec = EpistemicEvidenceRecord(
        run_id="run_001",
        claim_id="clm_001",
        artifact=EpistemicArtifactRef(
            artifact_id="art_001",
            content_sha256="a" * 64,
            relative_ref="artifacts/art_001.txt",
        ),
        extraction_ref="ext_001",
        assessment_ref="asm_001",
        cannot_establish_present=True,
        evidence_seal_status="FAIL",
    )
    object.__setattr__(inp, "records", (bad_rec,))

    res = build_epistemic_verification_result(inp)
    assert res.status == EpistemicIntegrityStatus.RETURN
    assert "EP_EVIDENCE_SEAL_STATUS_FAILED" in res.blockers


def test_existing_record_blocker_propagates():
    inp = _make_valid_input()
    bad_rec = EpistemicEvidenceRecord(
        run_id="run_001",
        claim_id="clm_001",
        artifact=EpistemicArtifactRef(
            artifact_id="art_001",
            content_sha256="a" * 64,
            relative_ref="artifacts/art_001.txt",
        ),
        extraction_ref="ext_001",
        assessment_ref="asm_001",
        cannot_establish_present=True,
        blockers=("custom_record_blocker",),
    )
    object.__setattr__(inp, "records", (bad_rec,))

    res = build_epistemic_verification_result(inp)
    assert res.status == EpistemicIntegrityStatus.RETURN
    assert "custom_record_blocker" in res.blockers


def test_evidence_refs_preserved():
    inp = _make_valid_input()
    res = build_epistemic_verification_result(inp)
    assert "ext_001" in res.evidence_refs
    assert "asm_001" in res.evidence_refs


def test_receipt_refs_preserved():
    inp = _make_valid_input()
    res = build_epistemic_verification_result(inp)
    assert "rcp_001" in res.receipt_refs


def test_runtime_update_remains_false():
    inp = _make_valid_input()
    read_model = build_epistemic_claim_evidence_read_model(inp)
    assert read_model["runtime_update_allowed"] is False


def test_public_benchmark_remains_false():
    inp = _make_valid_input()
    read_model = build_epistemic_claim_evidence_read_model(inp)
    assert read_model["public_benchmark_allowed"] is False


def test_public_claim_remains_false():
    inp = _make_valid_input()
    ext = build_epistemic_receipt_extension(inp)
    assert ext.to_dict()["public_claim_allowed"] is False


def test_producer_public_claim_injection_cannot_unlock():
    inp = _make_valid_input()
    ext = build_epistemic_receipt_extension(inp)
    d = ext.to_dict()
    assert d["public_claim_allowed"] is False
    assert d["production_ready"] is False


def test_receipt_extension_contains_claim_boundary_output():
    inp = _make_valid_input()
    ext = build_epistemic_receipt_extension(inp)
    assert isinstance(ext.claim_boundary, ClaimBoundary)
    assert ext.claim_boundary.public_claim_allowed is False
    assert ext.claim_boundary.production_ready is False


def test_no_raw_text_in_receipt_extension():
    inp = _make_valid_input()
    ext = build_epistemic_receipt_extension(inp)
    d = ext.to_dict()
    blob = str(d)
    assert "source_text" not in blob
    assert "full_text" not in blob
    assert "user_position" not in blob


def test_completion_failure_propagates():
    inp = _make_valid_input()
    object.__setattr__(inp, "completion_status", "FAIL")

    blockers = validate_epistemic_profile_input(inp)
    assert "EP_COMPLETION_STATUS_FAILED" in blockers

    res = build_epistemic_verification_result(inp)
    assert res.status == EpistemicIntegrityStatus.RETURN


def test_missing_completion_envelope_on_pass_fails_closed():
    inp = _make_valid_input()
    object.__setattr__(inp, "completion_envelope_ref", "")

    blockers = validate_epistemic_profile_input(inp)
    assert "EP_MISSING_COMPLETION_ENVELOPE_REF" in blockers


def test_multiple_records_remain_bound_to_one_run():
    inp = _make_valid_input()
    art2 = EpistemicArtifactRef(
        artifact_id="art_002",
        content_sha256="b" * 64,
        relative_ref="artifacts/art_002.txt",
    )
    rec2 = EpistemicEvidenceRecord(
        run_id="run_001",
        claim_id="clm_002",
        artifact=art2,
        extraction_ref="ext_002",
        assessment_ref="asm_002",
        direction=EpistemicDirection.CONTRADICTS,
        cannot_establish_present=True,
    )
    rec1 = inp.records[0]
    object.__setattr__(inp, "records", (rec1, rec2))

    blockers = validate_epistemic_profile_input(inp)
    assert len(blockers) == 0

    res = build_epistemic_verification_result(inp)
    assert res.status == EpistemicIntegrityStatus.PASS
    assert res.records_checked == 2
