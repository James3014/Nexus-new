"""
Strict Epistemic Profile Exporter Loader and Serializer (Read-Only Bridge).
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple, Union

from nexus.research.epistemic_profile.adapter import (
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
    EpistemicReceiptExtension,
    EpistemicScopeAlignment,
    EpistemicVerificationResult,
)

EXPECTED_EXPORT_SCHEMA = "research-ledger.nexus-epistemic-export.v1"

ALLOWED_EXPORT_TOP_LEVEL_KEYS: Set[str] = {
    "schema",
    "export_id",
    "exported_at",
    "task_id",
    "attempt_id",
    "profile_id",
    "run_id",
    "masked_brief_ref",
    "position_commitment_ref",
    "completion_status",
    "completion_envelope_ref",
    "records",
    "verification",
    "export_sha256",
}

FORBIDDEN_KEYS: Set[str] = {
    "source_text",
    "original_text",
    "full_text",
    "user_position",
    "position",
    "position_salt",
    "salt",
    "can_establish",
    "cannot_establish",
    "reasoning_steps",
    "chain_of_thought",
    "absolute_path",
    "sealed_path",
    "secret",
    "api_key",
    "token",
    "password",
}

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


def _scan_forbidden_keys(data: Any) -> List[str]:
    found = []
    if isinstance(data, dict):
        for k, v in data.items():
            if k in FORBIDDEN_KEYS:
                found.append(k)
            found.extend(_scan_forbidden_keys(v))
    elif isinstance(data, list):
        for item in data:
            found.extend(_scan_forbidden_keys(item))
    return found


def _validate_raw_export_dict(data: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any]]:
    blockers: List[str] = []

    schema = data.get("schema")
    if schema != EXPECTED_EXPORT_SCHEMA:
        blockers.append("EP_INVALID_SCHEMA")

    if set(data.keys()) != ALLOWED_EXPORT_TOP_LEVEL_KEYS:
        blockers.append("EP_EXPORT_KEYS_MISMATCH")

    # Forbidden key check at any depth
    forbidden = _scan_forbidden_keys(data)
    if forbidden:
        blockers.append("EP_FORBIDDEN_KEY_DETECTED")

    # Hash check
    export_sha256 = data.get("export_sha256", "")
    data_sans_hash = {k: v for k, v in data.items() if k != "export_sha256"}
    canonical_json = json.dumps(data_sans_hash, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    calculated_sha256 = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    if export_sha256 != calculated_sha256:
        blockers.append("EP_EXPORT_HASH_MISMATCH")

    # Type & Count validations
    records = data.get("records")
    if not isinstance(records, list):
        blockers.append("EP_INVALID_RECORDS_TYPE")
        records = []

    verification = data.get("verification", {})
    if isinstance(verification, dict):
        rec_exp = verification.get("records_exported")
        if rec_exp is not None and rec_exp != len(records):
            blockers.append("EP_RECORDS_COUNT_MISMATCH")
    else:
        blockers.append("EP_INVALID_VERIFICATION_TYPE")

    top_run_id = data.get("run_id", "")
    parsed_records: List[EpistemicEvidenceRecord] = []

    for idx, rec_dict in enumerate(records):
        if not isinstance(rec_dict, dict):
            blockers.append(f"EP_INVALID_RECORD_ITEM_{idx}")
            continue

        rec_run_id = rec_dict.get("run_id", "")
        if rec_run_id != top_run_id:
            blockers.append("EP_CROSS_RUN_RECORD")

        art_dict = rec_dict.get("artifact", {})
        if not isinstance(art_dict, dict):
            blockers.append(f"EP_INVALID_ARTIFACT_TYPE_{idx}")

        try:
            art_ref = EpistemicArtifactRef(
                artifact_id=str(art_dict.get("artifact_id", "")),
                content_sha256=str(art_dict.get("content_sha256", "")),
                relative_ref=str(art_dict.get("relative_ref", "")),
                lineage_ref=str(art_dict.get("lineage_ref", "")),
                lineage_independence=str(art_dict.get("lineage_independence", "unknown")),
            )
        except Exception:
            blockers.append(f"EP_INVALID_ARTIFACT_REF_{idx}")
            art_ref = EpistemicArtifactRef(
                artifact_id="invalid",
                content_sha256="0" * 64,
                relative_ref="invalid.txt",
            )

        dir_str = str(rec_dict.get("direction", "unknown")).lower()
        dir_enum = EpistemicDirection.UNKNOWN
        for e in EpistemicDirection:
            if e.value == dir_str:
                dir_enum = e
                break

        scope_str = str(rec_dict.get("scope_alignment", "unknown")).lower()
        scope_enum = EpistemicScopeAlignment.UNKNOWN
        for e in EpistemicScopeAlignment:
            if e.value == scope_str:
                scope_enum = e
                break

        cannot_est = bool(rec_dict.get("cannot_establish_present", False))

        try:
            rec_obj = EpistemicEvidenceRecord(
                run_id=str(rec_dict.get("run_id", "")),
                claim_id=str(rec_dict.get("claim_id", "")),
                artifact=art_ref,
                extraction_ref=str(rec_dict.get("extraction_ref", "")),
                assessment_ref=str(rec_dict.get("assessment_ref", "")),
                direction=dir_enum,
                scope_alignment=scope_enum,
                cannot_establish_present=cannot_est,
                evidence_hash_status=str(rec_dict.get("evidence_hash_status", "PASS")),
                evidence_seal_status=str(rec_dict.get("evidence_seal_status", "PASS")),
                receipt_refs=tuple(rec_dict.get("receipt_refs", ())),
                blockers=tuple(rec_dict.get("blockers", ())),
            )
            parsed_records.append(rec_obj)
        except Exception:
            blockers.append(f"EP_INVALID_EVIDENCE_RECORD_{idx}")

    return tuple(dict.fromkeys(blockers)), parsed_records


def load_epistemic_profile_export(source: Union[str, Path, Dict[str, Any]]) -> EpistemicProfileInput:
    if isinstance(source, (str, Path)):
        p = Path(source)
        if not p.exists():
            raise FileNotFoundError(f"Export file not found: {source}")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif isinstance(source, dict):
        data = source
    else:
        raise TypeError(f"Invalid export source type: {type(source)}")

    raw_io_blockers, parsed_records = _validate_raw_export_dict(data)
    io_blockers = list(raw_io_blockers)

    try:
        inp = EpistemicProfileInput(
            task_id=str(data.get("task_id", "")),
            attempt_id=str(data.get("attempt_id", "")),
            profile_id=str(data.get("profile_id", "")),
            run_id=str(data.get("run_id", "")),
            masked_brief_ref=str(data.get("masked_brief_ref", "")),
            position_commitment_ref=str(data.get("position_commitment_ref", "")),
            records=tuple(parsed_records),
            completion_status=str(data.get("completion_status", "NOT_APPLICABLE")),
            completion_envelope_ref=str(data.get("completion_envelope_ref", "")),
        )
    except ValueError as ve:
        io_blockers.append(str(ve))
        # Build safe fallback input
        bad_art = EpistemicArtifactRef(
            artifact_id="art_invalid",
            content_sha256="0" * 64,
            relative_ref="invalid.txt",
        )
        dummy_rec = EpistemicEvidenceRecord(
            run_id=str(data.get("run_id", "run_invalid")),
            claim_id="clm_invalid",
            artifact=bad_art,
            extraction_ref="ext_invalid",
            assessment_ref="asm_invalid",
            blockers=tuple(io_blockers),
        )
        inp = EpistemicProfileInput(
            task_id=str(data.get("task_id", "t_invalid")),
            attempt_id=str(data.get("attempt_id", "a_invalid")),
            profile_id=str(data.get("profile_id", "p_invalid")),
            run_id=str(data.get("run_id", "r_invalid")),
            masked_brief_ref=str(data.get("masked_brief_ref", "brief_invalid")),
            position_commitment_ref=str(data.get("position_commitment_ref", "pos_invalid")),
            records=(dummy_rec,),
            completion_status=str(data.get("completion_status", "NOT_APPLICABLE")),
            completion_envelope_ref=str(data.get("completion_envelope_ref", "")),
        )

    if io_blockers:
        updated_records = []
        for rec in inp.records:
            object.__setattr__(rec, "blockers", tuple(dict.fromkeys(list(rec.blockers) + list(io_blockers))))
            updated_records.append(rec)
        if not updated_records:
            bad_art = EpistemicArtifactRef(
                artifact_id="art_invalid",
                content_sha256="0" * 64,
                relative_ref="invalid.txt",
            )
            dummy_rec = EpistemicEvidenceRecord(
                run_id=inp.run_id or "run_invalid",
                claim_id="clm_invalid",
                artifact=bad_art,
                extraction_ref="ext_invalid",
                assessment_ref="asm_invalid",
                blockers=tuple(io_blockers),
            )
            updated_records.append(dummy_rec)
        object.__setattr__(inp, "records", tuple(updated_records))

    return inp


def verify_epistemic_profile_export(source: Union[str, Path, Dict[str, Any]]) -> EpistemicVerificationResult:
    inp = load_epistemic_profile_export(source)
    return build_epistemic_verification_result(inp)


def write_epistemic_receipt(
    result: Union[EpistemicVerificationResult, Dict[str, Any]],
    output_path: Union[str, Path],
) -> Dict[str, Any]:
    if isinstance(result, EpistemicVerificationResult):
        res_dict = result.to_dict()
    else:
        res_dict = dict(result)

    res_dict["runtime_update_allowed"] = False
    res_dict["public_claim_allowed"] = False
    res_dict["public_benchmark_allowed"] = False
    res_dict["production_ready"] = False
    res_dict["integration_approved"] = False

    # Scan for forbidden keys before writing
    forbidden = _scan_forbidden_keys(res_dict)
    if forbidden:
        raise ValueError(f"RECEIPT_FORBIDDEN_KEY_DETECTED: {forbidden}")

    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(res_dict, f, indent=2, ensure_ascii=False)

    return res_dict
