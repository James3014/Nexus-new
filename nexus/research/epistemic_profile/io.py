"""
Strict Epistemic Profile Exporter Loader and Serializer (Read-Only Bridge).
"""

import hashlib
import json
import os
import re
import uuid
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

EXPECTED_VERIFICATION_KEYS: Set[str] = {
    "gate_a_status",
    "evidence_pipeline_valid",
    "claim_ledger_valid",
    "adjudication_ledger_valid",
    "decision_trace_valid",
    "records_exported",
    "state_manifest_sha256",
}

EXPECTED_RECORD_KEYS: Set[str] = {
    "run_id",
    "claim_id",
    "artifact",
    "extraction_ref",
    "assessment_ref",
    "direction",
    "scope_alignment",
    "cannot_establish_present",
    "evidence_hash_status",
    "evidence_seal_status",
    "receipt_refs",
    "blockers",
}

EXPECTED_ARTIFACT_KEYS: Set[str] = {
    "artifact_id",
    "content_sha256",
    "relative_ref",
    "lineage_ref",
    "lineage_independence",
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

VALID_DIRECTIONS = {"supports", "contradicts", "contextual", "inconclusive", "unknown"}
VALID_SCOPE_ALIGNMENTS = {"matched", "partial", "mismatched", "unknown"}


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


def _validate_export_json_payload(data: Any) -> Tuple[List[str], List[EpistemicEvidenceRecord]]:
    blockers: List[str] = []

    if type(data) is not dict:
        return ["EP_EXPORT_KEYS_MISMATCH"], []

    if set(data.keys()) != ALLOWED_EXPORT_TOP_LEVEL_KEYS:
        blockers.append("EP_EXPORT_KEYS_MISMATCH")

    # Strict top-level string type checks (B3)
    str_keys = [
        "schema", "export_id", "exported_at", "task_id", "attempt_id",
        "profile_id", "run_id", "masked_brief_ref", "position_commitment_ref",
        "completion_status", "completion_envelope_ref", "export_sha256"
    ]
    for sk in str_keys:
        if sk in data and type(data[sk]) is not str:
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
    if type(export_sha256) is not str or export_sha256 != calculated_sha256:
        blockers.append("EP_EXPORT_HASH_MISMATCH")

    # Schema check
    if data.get("schema") != EXPECTED_EXPORT_SCHEMA:
        blockers.append("EP_INVALID_SCHEMA")

    # Verification dict validation (B2, B3, B5)
    ver = data.get("verification")
    if type(ver) is not dict:
        blockers.append("EP_VERIFICATION_KEYS_MISMATCH")
    else:
        if set(ver.keys()) != EXPECTED_VERIFICATION_KEYS:
            blockers.append("EP_VERIFICATION_KEYS_MISMATCH")

        # Type checks inside verification
        if type(ver.get("gate_a_status")) is not str:
            blockers.append("EP_VERIFICATION_KEYS_MISMATCH")
        if type(ver.get("evidence_pipeline_valid")) is not bool:
            blockers.append("EP_VERIFICATION_KEYS_MISMATCH")
        if type(ver.get("claim_ledger_valid")) is not bool:
            blockers.append("EP_VERIFICATION_KEYS_MISMATCH")
        if type(ver.get("adjudication_ledger_valid")) is not bool:
            blockers.append("EP_VERIFICATION_KEYS_MISMATCH")
        if type(ver.get("decision_trace_valid")) is not bool:
            blockers.append("EP_VERIFICATION_KEYS_MISMATCH")
        if type(ver.get("records_exported")) is not int:  # type(True) is bool, so type(x) is int rejects bools
            blockers.append("EP_VERIFICATION_KEYS_MISMATCH")
        if type(ver.get("state_manifest_sha256")) is not str:
            blockers.append("EP_VERIFICATION_KEYS_MISMATCH")

        # Semantics checks (B5)
        if ver.get("gate_a_status") != "GATE_A_VERIFIED":
            blockers.append("EP_GATE_A_NOT_VERIFIED")
        if ver.get("evidence_pipeline_valid") is not True:
            blockers.append("EP_EVIDENCE_PIPELINE_NOT_VERIFIED")
        if ver.get("claim_ledger_valid") is not True:
            blockers.append("EP_CLAIM_LEDGER_NOT_VERIFIED")
        if ver.get("adjudication_ledger_valid") is not True:
            blockers.append("EP_ADJUDICATION_LEDGER_NOT_VERIFIED")
        if ver.get("decision_trace_valid") is not True:
            blockers.append("EP_DECISION_TRACE_NOT_VERIFIED")

        manifest_sha = ver.get("state_manifest_sha256", "")
        if type(manifest_sha) is not str or not re.fullmatch(r"^[0-9a-f]{64}$", manifest_sha):
            blockers.append("EP_INVALID_STATE_MANIFEST_HASH")

    # Records list validation (B2, B3, B4)
    records = data.get("records")
    if type(records) is not list:
        blockers.append("EP_RECORD_KEYS_MISMATCH")
        records = []
    else:
        if ver and type(ver) is dict and type(ver.get("records_exported")) is int:
            if ver.get("records_exported") != len(records):
                blockers.append("EP_RECORDS_COUNT_MISMATCH")

    top_run_id = data.get("run_id", "")
    parsed_records: List[EpistemicEvidenceRecord] = []

    for idx, rec_dict in enumerate(records):
        if type(rec_dict) is not dict:
            blockers.append("EP_RECORD_KEYS_MISMATCH")
            continue

        if set(rec_dict.keys()) != EXPECTED_RECORD_KEYS:
            blockers.append("EP_RECORD_KEYS_MISMATCH")

        # Strict string type checks inside record
        rec_str_fields = ["run_id", "claim_id", "extraction_ref", "assessment_ref", "direction", "scope_alignment", "evidence_hash_status", "evidence_seal_status"]
        for rf in rec_str_fields:
            if rf in rec_dict and type(rec_dict[rf]) is not str:
                blockers.append("EP_RECORD_KEYS_MISMATCH")

        # Strict boolean type check (B3)
        if "cannot_establish_present" in rec_dict and type(rec_dict["cannot_establish_present"]) is not bool:
            blockers.append("EP_RECORD_KEYS_MISMATCH")

        # Strict list type checks
        if "receipt_refs" in rec_dict:
            if type(rec_dict["receipt_refs"]) is not list or any(type(x) is not str for x in rec_dict["receipt_refs"]):
                blockers.append("EP_RECORD_KEYS_MISMATCH")
        if "blockers" in rec_dict:
            if type(rec_dict["blockers"]) is not list or any(type(x) is not str for x in rec_dict["blockers"]):
                blockers.append("EP_RECORD_KEYS_MISMATCH")

        rec_run_id = rec_dict.get("run_id")
        if rec_run_id != top_run_id:
            blockers.append("EP_CROSS_RUN_RECORD")

        # Enums strict validation (B4)
        dir_val = rec_dict.get("direction", "")
        if dir_val not in VALID_DIRECTIONS:
            blockers.append("EP_INVALID_DIRECTION")

        scope_val = rec_dict.get("scope_alignment", "")
        if scope_val not in VALID_SCOPE_ALIGNMENTS:
            blockers.append("EP_INVALID_SCOPE_ALIGNMENT")

        # Artifact dict validation (B2, B3)
        art_dict = rec_dict.get("artifact")
        if type(art_dict) is not dict:
            blockers.append("EP_ARTIFACT_KEYS_MISMATCH")
            art_ref = EpistemicArtifactRef(
                artifact_id="invalid",
                content_sha256="0" * 64,
                relative_ref="invalid.txt",
            )
        else:
            if set(art_dict.keys()) != EXPECTED_ARTIFACT_KEYS:
                blockers.append("EP_ARTIFACT_KEYS_MISMATCH")

            art_str_fields = ["artifact_id", "content_sha256", "relative_ref", "lineage_ref", "lineage_independence"]
            for af in art_str_fields:
                if af in art_dict and type(art_dict[af]) is not str:
                    blockers.append("EP_ARTIFACT_KEYS_MISMATCH")

            try:
                art_ref = EpistemicArtifactRef(
                    artifact_id=str(art_dict.get("artifact_id", "")),
                    content_sha256=str(art_dict.get("content_sha256", "")),
                    relative_ref=str(art_dict.get("relative_ref", "")),
                    lineage_ref=str(art_dict.get("lineage_ref", "")),
                    lineage_independence=str(art_dict.get("lineage_independence", "unknown")),
                )
            except Exception:
                blockers.append("EP_INVALID_ARTIFACT_REF")
                art_ref = EpistemicArtifactRef(
                    artifact_id="invalid",
                    content_sha256="0" * 64,
                    relative_ref="invalid.txt",
                )

        dir_enum = EpistemicDirection.UNKNOWN
        for e in EpistemicDirection:
            if e.value == dir_val:
                dir_enum = e
                break

        scope_enum = EpistemicScopeAlignment.UNKNOWN
        for e in EpistemicScopeAlignment:
            if e.value == scope_val:
                scope_enum = e
                break

        try:
            rec_obj = EpistemicEvidenceRecord(
                run_id=str(rec_dict.get("run_id", "")),
                claim_id=str(rec_dict.get("claim_id", "")),
                artifact=art_ref,
                extraction_ref=str(rec_dict.get("extraction_ref", "")),
                assessment_ref=str(rec_dict.get("assessment_ref", "")),
                direction=dir_enum,
                scope_alignment=scope_enum,
                cannot_establish_present=bool(rec_dict.get("cannot_establish_present", False)),
                evidence_hash_status=str(rec_dict.get("evidence_hash_status", "PASS")),
                evidence_seal_status=str(rec_dict.get("evidence_seal_status", "PASS")),
                receipt_refs=tuple(rec_dict.get("receipt_refs", [])),
                blockers=tuple(rec_dict.get("blockers", [])),
            )
            parsed_records.append(rec_obj)
        except Exception:
            blockers.append(f"EP_INVALID_EVIDENCE_RECORD_{idx}")

    return tuple(dict.fromkeys(blockers)), parsed_records


def load_epistemic_profile_export(source: Union[str, Path, Dict[str, Any]]) -> EpistemicProfileInput:
    if isinstance(source, (str, Path)):
        p = Path(source).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Export file not found: {source}")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif isinstance(source, dict):
        data = source
    else:
        raise TypeError(f"Invalid export source type: {type(source)}")

    io_blockers, parsed_records = _validate_export_json_payload(data)

    inp = EpistemicProfileInput(
        task_id=str(data.get("task_id", "")) if type(data.get("task_id")) is str else "invalid",
        attempt_id=str(data.get("attempt_id", "")) if type(data.get("attempt_id")) is str else "invalid",
        profile_id=str(data.get("profile_id", "")) if type(data.get("profile_id")) is str else "invalid",
        run_id=str(data.get("run_id", "")) if type(data.get("run_id")) is str else "invalid",
        masked_brief_ref=str(data.get("masked_brief_ref", "")) if type(data.get("masked_brief_ref")) is str else "invalid",
        position_commitment_ref=str(data.get("position_commitment_ref", "")) if type(data.get("position_commitment_ref")) is str else "invalid",
        records=tuple(parsed_records),
        completion_status=str(data.get("completion_status", "NOT_APPLICABLE")) if type(data.get("completion_status")) is str else "INVALID",
        completion_envelope_ref=str(data.get("completion_envelope_ref", "")) if type(data.get("completion_envelope_ref")) is str else "invalid",
    )

    return inp


def verify_epistemic_profile_export(source: Union[str, Path, Dict[str, Any]]) -> EpistemicVerificationResult:
    source_path: Union[Path, None] = None
    stat_before = None
    sha_before = None

    if isinstance(source, (str, Path)):
        source_path = Path(source).resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Export file not found: {source}")
        stat_before = source_path.stat()
        sha_before = hashlib.sha256(source_path.read_bytes()).hexdigest()
        with open(source_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif isinstance(source, dict):
        data = source
    else:
        raise TypeError(f"Invalid export source type: {type(source)}")

    io_blockers, parsed_records = _validate_export_json_payload(data)

    ver_meta = data.get("verification", {}) if isinstance(data, dict) and isinstance(data.get("verification"), dict) else {}
    manifest_sha = str(ver_meta.get("state_manifest_sha256", "")) if isinstance(ver_meta, dict) else ""

    meta_kwargs = {
        "source_schema": str(data.get("schema", "")) if isinstance(data, dict) else "",
        "source_export_id": str(data.get("export_id", "")) if isinstance(data, dict) else "",
        "source_export_sha256": str(data.get("export_sha256", "")) if isinstance(data, dict) else "",
        "source_state_manifest_sha256": manifest_sha,
        "source_task_id": str(data.get("task_id", "")) if isinstance(data, dict) else "",
        "source_attempt_id": str(data.get("attempt_id", "")) if isinstance(data, dict) else "",
        "source_profile_id": str(data.get("profile_id", "")) if isinstance(data, dict) else "",
        "source_run_id": str(data.get("run_id", "")) if isinstance(data, dict) else "",
    }

    if io_blockers:
        res = EpistemicVerificationResult(
            status=EpistemicIntegrityStatus.RETURN,
            records_checked=len(parsed_records),
            evidence_refs=(),
            receipt_refs=(),
            blockers=tuple(io_blockers),
            claim_evidence_read_model={},
            **meta_kwargs,
        )
    else:
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
        base_res = build_epistemic_verification_result(inp)
        res = EpistemicVerificationResult(
            status=base_res.status,
            records_checked=base_res.records_checked,
            evidence_refs=base_res.evidence_refs,
            receipt_refs=base_res.receipt_refs,
            blockers=base_res.blockers,
            claim_evidence_read_model=base_res.claim_evidence_read_model,
            **meta_kwargs,
        )

    # Input file non-mutating check (B8)
    if source_path:
        stat_after = source_path.stat()
        sha_after = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if sha_before != sha_after or stat_before.st_mtime_ns != stat_after.st_mtime_ns:
            raise RuntimeError(f"INPUT_MUTATED_DURING_VERIFY: export file {source_path} was mutated during verification!")

    return res


def write_epistemic_receipt(
    result: Union[EpistemicVerificationResult, Dict[str, Any]],
    output_path: Union[str, Path],
    source_export_path: Union[str, Path, None] = None,
) -> Dict[str, Any]:
    out_p = Path(output_path).resolve()

    if source_export_path:
        in_p = Path(source_export_path).resolve()
        if out_p == in_p:
            raise ValueError(f"RECEIPT_OUTPUT_OVERWRITES_INPUT: receipt path {out_p} equals input path {in_p}")
        if in_p.exists() and out_p.exists() and os.path.samefile(out_p, in_p):
            raise ValueError(f"RECEIPT_OUTPUT_OVERWRITES_INPUT: receipt path {out_p} shares inode with input path {in_p}")

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

    # Atomic receipt writing (B8)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    temp_receipt = out_p.parent / f".tmp_receipt_{uuid.uuid4().hex[:12]}.json"

    try:
        with open(temp_receipt, "w", encoding="utf-8") as f:
            json.dump(res_dict, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_receipt, out_p)
    except Exception as exc:
        if temp_receipt.exists():
            try:
                temp_receipt.unlink()
            except OSError:
                pass
        raise exc

    return res_dict
