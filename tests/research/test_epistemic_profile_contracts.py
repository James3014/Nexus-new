from __future__ import annotations

import pytest

from nexus.research.epistemic_profile.contracts import (
    EPISTEMIC_ARTIFACT_REF_SCHEMA,
    EPISTEMIC_EVIDENCE_RECORD_SCHEMA,
    EPISTEMIC_PROFILE_INPUT_SCHEMA,
    EPISTEMIC_RECEIPT_EXTENSION_SCHEMA,
    EPISTEMIC_VERIFICATION_RESULT_SCHEMA,
    EpistemicArtifactRef,
    EpistemicDirection,
    EpistemicEvidenceRecord,
    EpistemicIntegrityStatus,
    EpistemicProfileInput,
    EpistemicReceiptExtension,
    EpistemicScopeAlignment,
    EpistemicVerificationResult,
)


def test_valid_artifact_ref_round_trip():
    ref = EpistemicArtifactRef(
        artifact_id="art_001",
        content_sha256="a" * 64,
        relative_ref="artifacts/art_001.txt",
        lineage_ref="lin_001",
        lineage_independence="independent",
    )
    d = ref.to_dict()
    assert d["artifact_id"] == "art_001"
    assert d["content_sha256"] == "a" * 64
    assert d["relative_ref"] == "artifacts/art_001.txt"
    assert d["schema"] == EPISTEMIC_ARTIFACT_REF_SCHEMA


def test_reject_absolute_path_in_artifact_ref():
    with pytest.raises(ValueError, match="relative reference"):
        EpistemicArtifactRef(
            artifact_id="art_001",
            content_sha256="a" * 64,
            relative_ref="/etc/passwd",
        )


def test_reject_traversal_in_artifact_ref():
    with pytest.raises(ValueError, match="path traversal"):
        EpistemicArtifactRef(
            artifact_id="art_001",
            content_sha256="a" * 64,
            relative_ref="../secret.txt",
        )


def test_reject_empty_relative_ref():
    with pytest.raises(ValueError, match="relative_ref"):
        EpistemicArtifactRef(
            artifact_id="art_001",
            content_sha256="a" * 64,
            relative_ref="  ",
        )


def test_reject_invalid_sha256():
    with pytest.raises(ValueError, match="64-character lowercase hex"):
        EpistemicArtifactRef(
            artifact_id="art_001",
            content_sha256="INVALID_HASH",
            relative_ref="artifacts/art_001.txt",
        )


def test_reject_empty_claim_id():
    art = EpistemicArtifactRef(
        artifact_id="art_001",
        content_sha256="a" * 64,
        relative_ref="artifacts/art_001.txt",
    )
    with pytest.raises(ValueError, match="claim_id"):
        EpistemicEvidenceRecord(
            run_id="run_001",
            claim_id="  ",
            artifact=art,
            extraction_ref="ext_001",
            assessment_ref="asm_001",
            cannot_establish_present=True,
        )


def test_evidence_record_round_trip():
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
    )
    d = rec.to_dict()
    assert d["run_id"] == "run_001"
    assert d["direction"] == "supports"
    assert d["cannot_establish_present"] is True
    assert d["schema"] == EPISTEMIC_EVIDENCE_RECORD_SCHEMA


def test_no_source_full_text_or_user_position_fields():
    rec_dict = EpistemicEvidenceRecord(
        run_id="run_001",
        claim_id="clm_001",
        artifact=EpistemicArtifactRef(
            artifact_id="art_001",
            content_sha256="a" * 64,
            relative_ref="artifacts/art_001.txt",
        ),
        extraction_ref="ext_001",
        assessment_ref="asm_001",
        direction=EpistemicDirection.SUPPORTS,
        cannot_establish_present=True,
    ).to_dict()

    assert "source_text" not in rec_dict
    assert "full_text" not in rec_dict
    assert "user_position" not in rec_dict
    assert "position_salt" not in rec_dict


def test_supports_requires_cannot_establish_presence():
    with pytest.raises(ValueError, match="cannot_establish_present"):
        EpistemicEvidenceRecord(
            run_id="run_001",
            claim_id="clm_001",
            artifact=EpistemicArtifactRef(
                artifact_id="art_001",
                content_sha256="a" * 64,
                relative_ref="artifacts/art_001.txt",
            ),
            extraction_ref="ext_001",
            assessment_ref="asm_001",
            direction=EpistemicDirection.SUPPORTS,
            cannot_establish_present=False,
        )


def test_contradicts_requires_cannot_establish_presence():
    with pytest.raises(ValueError, match="cannot_establish_present"):
        EpistemicEvidenceRecord(
            run_id="run_001",
            claim_id="clm_001",
            artifact=EpistemicArtifactRef(
                artifact_id="art_001",
                content_sha256="a" * 64,
                relative_ref="artifacts/art_001.txt",
            ),
            extraction_ref="ext_001",
            assessment_ref="asm_001",
            direction=EpistemicDirection.CONTRADICTS,
            cannot_establish_present=False,
        )


def test_profile_requires_masked_brief_ref():
    rec = EpistemicEvidenceRecord(
        run_id="run_001",
        claim_id="clm_001",
        artifact=EpistemicArtifactRef(
            artifact_id="art_001",
            content_sha256="a" * 64,
            relative_ref="artifacts/art_001.txt",
        ),
        extraction_ref="ext_001",
        assessment_ref="asm_001",
        direction=EpistemicDirection.SUPPORTS,
        cannot_establish_present=True,
    )
    with pytest.raises(ValueError, match="masked_brief_ref"):
        EpistemicProfileInput(
            task_id="task_001",
            attempt_id="att_001",
            profile_id="prof_001",
            run_id="run_001",
            masked_brief_ref="",
            position_commitment_ref="pos_001",
            records=(rec,),
        )


def test_profile_requires_position_commitment_ref():
    rec = EpistemicEvidenceRecord(
        run_id="run_001",
        claim_id="clm_001",
        artifact=EpistemicArtifactRef(
            artifact_id="art_001",
            content_sha256="a" * 64,
            relative_ref="artifacts/art_001.txt",
        ),
        extraction_ref="ext_001",
        assessment_ref="asm_001",
        direction=EpistemicDirection.SUPPORTS,
        cannot_establish_present=True,
    )
    with pytest.raises(ValueError, match="position_commitment_ref"):
        EpistemicProfileInput(
            task_id="task_001",
            attempt_id="att_001",
            profile_id="prof_001",
            run_id="run_001",
            masked_brief_ref="brief_001",
            position_commitment_ref="",
            records=(rec,),
        )


def test_profile_rejects_cross_run_record():
    rec_cross = EpistemicEvidenceRecord(
        run_id="run_OTHER",
        claim_id="clm_001",
        artifact=EpistemicArtifactRef(
            artifact_id="art_001",
            content_sha256="a" * 64,
            relative_ref="artifacts/art_001.txt",
        ),
        extraction_ref="ext_001",
        assessment_ref="asm_001",
        direction=EpistemicDirection.SUPPORTS,
        cannot_establish_present=True,
    )
    with pytest.raises(ValueError, match="run_id mismatch"):
        EpistemicProfileInput(
            task_id="task_001",
            attempt_id="att_001",
            profile_id="prof_001",
            run_id="run_001",
            masked_brief_ref="brief_001",
            position_commitment_ref="pos_001",
            records=(rec_cross,),
        )


def test_receipt_extension_contains_only_bounded_metadata():
    ext = EpistemicReceiptExtension(
        profile_id="prof_001",
        run_id="run_001",
        records_checked=1,
        evidence_refs=("ext_001",),
        receipt_refs=("rcp_001",),
    )
    d = ext.to_dict()
    assert d["schema"] == EPISTEMIC_RECEIPT_EXTENSION_SCHEMA
    assert "source_text" not in d
    assert "user_position" not in d
    assert "absolute_path" not in d


def test_locked_flags_remain_false():
    ext = EpistemicReceiptExtension(
        profile_id="prof_001",
        run_id="run_001",
    )
    d = ext.to_dict()
    assert d["runtime_update_allowed"] is False
    assert d["public_benchmark_allowed"] is False
    assert d["public_claim_allowed"] is False
    assert d["production_ready"] is False
    assert d["integration_approved"] is False
