from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
import pytest

from nexus.research.epistemic_profile.contracts import EpistemicIntegrityStatus
from nexus.research.epistemic_profile.io import (
    load_epistemic_profile_export,
    verify_epistemic_profile_export,
    write_epistemic_receipt,
)


def _make_valid_export_dict() -> dict:
    rec = {
        "run_id": "run_001",
        "claim_id": "clm_001",
        "artifact": {
            "artifact_id": "art_001",
            "content_sha256": "a" * 64,
            "relative_ref": "artifacts/art_001.txt",
            "lineage_ref": "lin_001",
            "lineage_independence": "independent",
        },
        "extraction_ref": "ext_001",
        "assessment_ref": "asm_001",
        "direction": "supports",
        "scope_alignment": "matched",
        "cannot_establish_present": True,
        "evidence_hash_status": "PASS",
        "evidence_seal_status": "PASS",
        "receipt_refs": ["event:rcp_001"],
        "blockers": [],
    }
    payload = {
        "schema": "research-ledger.nexus-epistemic-export.v1",
        "export_id": "exp_001",
        "exported_at": "2026-08-02T12:00:00Z",
        "task_id": "task_001",
        "attempt_id": "att_001",
        "profile_id": "prof_001",
        "run_id": "run_001",
        "masked_brief_ref": "public/blind-task.json",
        "position_commitment_ref": "event:evt_pos_001",
        "completion_status": "PASS",
        "completion_envelope_ref": "gate-a:run_001",
        "records": [rec],
        "verification": {
            "gate_a_status": "GATE_A_VERIFIED",
            "evidence_pipeline_valid": True,
            "claim_ledger_valid": True,
            "adjudication_ledger_valid": True,
            "decision_trace_valid": True,
            "records_exported": 1,
            "state_manifest_sha256": "b" * 64,
        },
    }
    canonical_json = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    payload["export_sha256"] = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return payload


def _rehash(payload: dict) -> dict:
    p = {k: v for k, v in payload.items() if k != "export_sha256"}
    canonical = json.dumps(p, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    payload["export_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def test_valid_export_dict_loads_cleanly():
    exp_dict = _make_valid_export_dict()
    inp = load_epistemic_profile_export(exp_dict)
    assert inp.task_id == "task_001"
    assert inp.run_id == "run_001"
    assert len(inp.records) == 1

    res = verify_epistemic_profile_export(exp_dict)
    assert res.status == EpistemicIntegrityStatus.PASS
    assert res.records_checked == 1
    assert res.source_export_id == "exp_001"
    assert res.source_export_sha256 == exp_dict["export_sha256"]


def test_unknown_schema_fails_closed():
    exp_dict = _make_valid_export_dict()
    exp_dict["schema"] = "unknown.schema.v99"
    exp_dict = _rehash(exp_dict)

    res = verify_epistemic_profile_export(exp_dict)
    assert res.status == EpistemicIntegrityStatus.RETURN
    assert "EP_INVALID_SCHEMA" in res.blockers


def test_extra_top_level_key_fails_closed():
    payload = _make_valid_export_dict()
    payload["unauthorized_key"] = "attacker_data"
    payload = _rehash(payload)

    res = verify_epistemic_profile_export(payload)
    assert res.status == EpistemicIntegrityStatus.RETURN
    assert "EP_EXPORT_KEYS_MISMATCH" in res.blockers


def test_extra_verification_key_fails_closed():
    payload = _make_valid_export_dict()
    payload["verification"]["extra_key"] = True
    payload = _rehash(payload)

    res = verify_epistemic_profile_export(payload)
    assert res.status == EpistemicIntegrityStatus.RETURN
    assert "EP_VERIFICATION_KEYS_MISMATCH" in res.blockers


def test_extra_record_key_fails_closed():
    payload = _make_valid_export_dict()
    payload["records"][0]["extra_rec_key"] = "bogus"
    payload = _rehash(payload)

    res = verify_epistemic_profile_export(payload)
    assert res.status == EpistemicIntegrityStatus.RETURN
    assert "EP_RECORD_KEYS_MISMATCH" in res.blockers


def test_extra_artifact_key_fails_closed():
    payload = _make_valid_export_dict()
    payload["records"][0]["artifact"]["extra_art_key"] = "bogus"
    payload = _rehash(payload)

    res = verify_epistemic_profile_export(payload)
    assert res.status == EpistemicIntegrityStatus.RETURN
    assert "EP_ARTIFACT_KEYS_MISMATCH" in res.blockers


def test_string_boolean_fails_closed():
    payload = _make_valid_export_dict()
    payload["records"][0]["cannot_establish_present"] = "false"
    payload = _rehash(payload)

    res = verify_epistemic_profile_export(payload)
    assert res.status == EpistemicIntegrityStatus.RETURN
    assert "EP_RECORD_KEYS_MISMATCH" in res.blockers


def test_integer_id_fails_closed():
    payload = _make_valid_export_dict()
    payload["task_id"] = 123
    payload = _rehash(payload)

    res = verify_epistemic_profile_export(payload)
    assert res.status == EpistemicIntegrityStatus.RETURN
    assert "EP_EXPORT_KEYS_MISMATCH" in res.blockers


def test_string_receipt_refs_fails_closed():
    payload = _make_valid_export_dict()
    payload["records"][0]["receipt_refs"] = "event:rcp_001"
    payload = _rehash(payload)

    res = verify_epistemic_profile_export(payload)
    assert res.status == EpistemicIntegrityStatus.RETURN
    assert "EP_RECORD_KEYS_MISMATCH" in res.blockers


def test_boolean_records_exported_fails_closed():
    payload = _make_valid_export_dict()
    payload["verification"]["records_exported"] = True
    payload = _rehash(payload)

    res = verify_epistemic_profile_export(payload)
    assert res.status == EpistemicIntegrityStatus.RETURN
    assert "EP_VERIFICATION_KEYS_MISMATCH" in res.blockers


def test_invalid_direction_fails_closed():
    payload = _make_valid_export_dict()
    payload["records"][0]["direction"] = "super_supported"
    payload = _rehash(payload)

    res = verify_epistemic_profile_export(payload)
    assert res.status == EpistemicIntegrityStatus.RETURN
    assert "EP_INVALID_DIRECTION" in res.blockers


def test_invalid_scope_alignment_fails_closed():
    payload = _make_valid_export_dict()
    payload["records"][0]["scope_alignment"] = "full"
    payload = _rehash(payload)

    res = verify_epistemic_profile_export(payload)
    assert res.status == EpistemicIntegrityStatus.RETURN
    assert "EP_INVALID_SCOPE_ALIGNMENT" in res.blockers


def test_corrupted_gate_a_status_fails_closed():
    payload = _make_valid_export_dict()
    payload["verification"]["gate_a_status"] = "GATE_A_CORRUPTED"
    payload = _rehash(payload)

    res = verify_epistemic_profile_export(payload)
    assert res.status == EpistemicIntegrityStatus.RETURN
    assert "EP_GATE_A_NOT_VERIFIED" in res.blockers


def test_false_subsystem_flag_fails_closed():
    payload = _make_valid_export_dict()
    payload["verification"]["evidence_pipeline_valid"] = False
    payload = _rehash(payload)

    res = verify_epistemic_profile_export(payload)
    assert res.status == EpistemicIntegrityStatus.RETURN
    assert "EP_EVIDENCE_PIPELINE_NOT_VERIFIED" in res.blockers


def test_invalid_state_manifest_hash_fails_closed():
    payload = _make_valid_export_dict()
    payload["verification"]["state_manifest_sha256"] = "invalid_hash"
    payload = _rehash(payload)

    res = verify_epistemic_profile_export(payload)
    assert res.status == EpistemicIntegrityStatus.RETURN
    assert "EP_INVALID_STATE_MANIFEST_HASH" in res.blockers


def test_verification_is_non_mutating_on_input_file():
    payload = _make_valid_export_dict()
    with tempfile.TemporaryDirectory() as tmpdir:
        input_file = Path(tmpdir) / "export.json"
        with open(input_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        stat_before = input_file.stat()
        sha_before = hashlib.sha256(input_file.read_bytes()).hexdigest()

        res = verify_epistemic_profile_export(input_file)
        assert res.status == EpistemicIntegrityStatus.PASS

        stat_after = input_file.stat()
        sha_after = hashlib.sha256(input_file.read_bytes()).hexdigest()

        assert sha_before == sha_after
        assert stat_before.st_mtime_ns == stat_after.st_mtime_ns


def test_receipt_overwriting_input_rejected():
    payload = _make_valid_export_dict()
    res = verify_epistemic_profile_export(payload)
    with tempfile.TemporaryDirectory() as tmpdir:
        export_file = Path(tmpdir) / "export.json"
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        with pytest.raises(ValueError, match="RECEIPT_OUTPUT_OVERWRITES_INPUT"):
            write_epistemic_receipt(res, export_file, source_export_path=export_file)
