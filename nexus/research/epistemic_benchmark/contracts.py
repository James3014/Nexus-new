"""
Epistemic Workflow Benchmark v0 — Contracts and Schema Definitions.

Closed enums, schema constants, and dataclass contracts.
All validation is strict: unknown values are rejected.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

BENCHMARK_CASE_SCHEMA = "nexus.epistemic_benchmark_case.v0"
BENCHMARK_ORACLE_SCHEMA = "nexus.epistemic_benchmark_oracle.v0"
BENCHMARK_ARM_SCHEMA = "nexus.epistemic_benchmark_arm.v0"
BENCHMARK_PACKET_SCHEMA = "nexus.epistemic_benchmark_packet.v0"
BENCHMARK_RUN_SCHEMA = "nexus.epistemic_benchmark_run.v0"
BENCHMARK_OBSERVATION_SCHEMA = "nexus.epistemic_benchmark_observation.v0"
BENCHMARK_REPORT_SCHEMA = "nexus.epistemic_benchmark_report.v0"
BENCHMARK_PRIVATE_CONTEXT_SCHEMA = "nexus.epistemic_benchmark_private_context.v0"
BENCHMARK_PUBLIC_MANIFEST_SCHEMA = "nexus.epistemic_benchmark_public_manifest.v0"

# ---------------------------------------------------------------------------
# Private Context Contract
# ---------------------------------------------------------------------------

PRIVATE_CONTEXT_EXACT_KEYS: Set[str] = {
    "schema", "benchmark_run_id", "corpus_version", "seed",
    "blinding_key_hex", "alias_bindings", "oracle_corpus_sha256",
    "public_manifest_sha256", "private_context_sha256",
}

PRIVATE_CONTEXT_BINDING_KEYS: Set[str] = {"arm", "case_alias", "case_id"}

# ---------------------------------------------------------------------------
# Public Manifest Contract
# ---------------------------------------------------------------------------

PUBLIC_MANIFEST_EXACT_KEYS: Set[str] = {
    "schema", "benchmark_run_id", "corpus_version", "created_at",
    "arms", "case_count", "packets", "run_manifest_sha256",
}

PUBLIC_MANIFEST_PACKET_EXACT_KEYS: Set[str] = {
    "arm", "case_alias", "relative_path", "packet_sha256", "common_materials_sha256",
}

PUBLIC_MANIFEST_FORBIDDEN_KEYS: Set[str] = {
    "seed", "case_id", "packet_manifest", "alias_to_case", "blinding_key",
    "blinding_key_hex", "private_context", "oracle", "expected_answer", "known_defects",
}

# ---------------------------------------------------------------------------
# Closed enums
# ---------------------------------------------------------------------------

class BenchmarkArm(str, Enum):
    STANDARD_REVIEW = "standard_review"
    STRONG_PROTOCOL = "strong_protocol"
    EPISTEMIC_WORKFLOW = "epistemic_workflow"


class BenchmarkDecision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    BLOCK = "BLOCK"


class OracleClass(str, Enum):
    CLEAN = "CLEAN"
    DEFECTIVE = "DEFECTIVE"
    INDETERMINATE = "INDETERMINATE"


class DefectSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Forbidden values that must never appear as status assertions
FORBIDDEN_TRUTH_STATUSES: Set[str] = {
    "TRUE", "FALSE", "PROVEN", "FINAL", "PRODUCTION_READY",
    "ARM_C_WINS", "LEDGER_PROVEN", "RESEARCH_IMPROVED",
    "STATISTICALLY_SIGNIFICANT",
}

# ---------------------------------------------------------------------------
# Epistemic Projection Contract constants
# ---------------------------------------------------------------------------

PROJECTION_EXACT_KEYS: Set[str] = {
    "object_bindings",
    "source_lineage",
    "extraction_assessment_separation",
    "verification_status",
    "cannot_establish_flags",
    "conflicts",
    "authority_locks",
    "review_report",
    "projection_sha256",
}

PROJECTION_OBJECT_BINDING_KEYS: Set[str] = {
    "object_id", "target_name", "status", "evidence_refs",
}
PROJECTION_OBJECT_BINDING_STATUS: Set[str] = {"BOUND", "MISMATCHED", "MISSING", "UNKNOWN"}

PROJECTION_SOURCE_LINEAGE_KEYS: Set[str] = {
    "lineage_id", "independence", "evidence_refs",
}
PROJECTION_LINEAGE_INDEPENDENCE: Set[str] = {
    "independent", "derivative", "shared_origin", "unknown",
}

PROJECTION_EXTRACTION_KEYS: Set[str] = {
    "claim_id", "direction", "evidence_refs",
}
PROJECTION_DIRECTION: Set[str] = {
    "supports", "contradicts", "contextual", "inconclusive", "unknown",
}

PROJECTION_VERIFICATION_KEYS: Set[str] = {
    "check_name", "status", "evidence_refs",
}
PROJECTION_VERIFICATION_STATUS: Set[str] = {"PASS", "FAIL", "NOT_RUN", "UNKNOWN"}

PROJECTION_CANNOT_ESTABLISH_KEYS: Set[str] = {
    "claim_id", "present", "evidence_refs",
}

PROJECTION_CONFLICT_KEYS: Set[str] = {
    "claim_id", "present", "evidence_refs",
}

PROJECTION_AUTHORITY_LOCK_KEYS: Set[str] = {
    "runtime_update_allowed",
    "public_claim_allowed",
    "public_benchmark_allowed",
    "production_ready",
    "integration_approved",
}

PROJECTION_REVIEW_REPORT_KEYS: Set[str] = {
    "schema", "object_count", "warning_codes", "evidence_refs", "projection_sha256",
}

PROJECTION_REVIEW_REPORT_SCHEMA = "nexus.epistemic_benchmark_projection_report.v0"

# Keys that are absolutely forbidden anywhere in a projection (recursive scan)
PROJECTION_FORBIDDEN_KEYS: Set[str] = {
    "oracle", "oracle_class", "oracle_decision", "known_defects",
    "required_detection", "expected_answer", "recommended_decision",
    "defect_description", "chain_of_thought", "reasoning_steps",
}

# Stable ID patterns for Epistemic Projection (Section B2)
_SHA256_LEAF_RE = re.compile(r"^[0-9a-f]{64}$")
_SCHEMA_LEAF_RE = re.compile(r"^nexus\.")
_OBJECT_ID_RE = re.compile(r"^OBJ-[A-Z0-9_-]+$")
_TARGET_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_-]{1,63}$")
_LINEAGE_ID_RE = re.compile(r"^LIN-[A-Z0-9_-]+$")
_CLAIM_ID_RE = re.compile(r"^CLM-[A-Z0-9_-]+$")
_CHECK_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
_WARNING_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")

_PROJECTION_CLOSED_ENUMS: Set[str] = {
    "BOUND", "MISMATCHED", "MISSING", "UNKNOWN",
    "independent", "derivative", "shared_origin", "unknown",
    "supports", "contradicts", "contextual", "inconclusive",
    "PASS", "FAIL", "NOT_RUN",
}

# ---------------------------------------------------------------------------
# SHA-256 utilities
# ---------------------------------------------------------------------------

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_canonical_sha256(obj: Any) -> str:
    """Return SHA-256 of canonical JSON of obj."""
    return _sha256(_canonical_json(obj))


def validate_sha256(value: str) -> bool:
    return bool(value and _SHA256_HEX_RE.match(value))


# ---------------------------------------------------------------------------
# Case Material
# ---------------------------------------------------------------------------

CASE_MATERIAL_KEYS: Set[str] = {"ref", "type", "sha256", "content"}


def validate_case_material(m: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    keys = set(m.keys())
    if keys != CASE_MATERIAL_KEYS:
        errors.append(f"MATERIAL_KEYS_MISMATCH: got {sorted(keys)}")
    if not m.get("ref") or not isinstance(m.get("ref"), str):
        errors.append("MATERIAL_REF_MISSING")
    if not m.get("type") or not isinstance(m.get("type"), str):
        errors.append("MATERIAL_TYPE_MISSING")
    sha = m.get("sha256", "")
    if not validate_sha256(sha):
        errors.append(f"MATERIAL_SHA256_INVALID: {sha!r}")
    else:
        content = m.get("content", "")
        computed = _sha256(content if isinstance(content, str) else _canonical_json(content))
        if computed != sha:
            errors.append(f"MATERIAL_SHA256_MISMATCH: ref={m.get('ref')}")
    return errors


# ---------------------------------------------------------------------------
# Benchmark Case Contract
# ---------------------------------------------------------------------------

CASE_EXACT_KEYS: Set[str] = {
    "schema", "case_id", "case_version", "title_neutral", "task_contract",
    "candidate_summary", "materials", "available_evidence_refs",
    "response_contract", "public_case_sha256", "epistemic_projection",
}

# Keys that must NOT appear in public case
CASE_FORBIDDEN_KEYS: Set[str] = {
    "oracle", "oracle_class", "oracle_decision", "known_defects",
    "expected_answer", "required_detection", "defect_ids",
}


def validate_public_case(case: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    keys = set(case.keys())

    # Exact keys check
    missing = CASE_EXACT_KEYS - keys
    extra = keys - CASE_EXACT_KEYS
    if missing:
        errors.append(f"CASE_MISSING_KEYS: {sorted(missing)}")
    if extra:
        errors.append(f"CASE_EXTRA_KEYS: {sorted(extra)}")

    # Forbidden keys
    leaked = CASE_FORBIDDEN_KEYS & keys
    if leaked:
        errors.append(f"CASE_FORBIDDEN_KEYS: {sorted(leaked)}")

    # Required string fields
    for fld in ("case_id", "case_version", "title_neutral", "task_contract",
                "candidate_summary", "response_contract"):
        val = case.get(fld)
        if not val or not isinstance(val, str) or not val.strip():
            errors.append(f"CASE_FIELD_MISSING_OR_EMPTY: {fld}")

    # Materials
    materials = case.get("materials", [])
    if not isinstance(materials, list) or len(materials) < 2:
        errors.append("CASE_INSUFFICIENT_MATERIALS")
    else:
        refs = [m.get("ref") for m in materials]
        if refs != sorted(refs):
            errors.append("CASE_MATERIALS_NOT_SORTED")
        if len(set(refs)) != len(refs):
            errors.append("CASE_DUPLICATE_REFS")
        for m in materials:
            errors.extend(validate_case_material(m))

    # Evidence refs
    ev_refs = case.get("available_evidence_refs", [])
    if not isinstance(ev_refs, list) or len(ev_refs) < 1:
        errors.append("CASE_NO_EVIDENCE_REFS")

    # Epistemic projection (Section D)
    proj = case.get("epistemic_projection")
    if proj is not None:
        material_refs: Set[str] = set()
        for m in (materials if isinstance(materials, list) else []):
            if isinstance(m, dict) and m.get("ref"):
                material_refs.add(m["ref"])
        if isinstance(ev_refs, list):
            for r in ev_refs:
                if r:
                    material_refs.add(r)
        proj_errors = validate_epistemic_projection(proj, material_refs)
        for pe in proj_errors:
            errors.append(f"PROJECTION_ERROR: {pe}")

    # Hash
    sha = case.get("public_case_sha256", "")
    if not validate_sha256(sha):
        errors.append(f"CASE_SHA256_INVALID: {sha!r}")
    else:
        body = {k: v for k, v in case.items() if k != "public_case_sha256"}
        expected = compute_canonical_sha256(body)
        if expected != sha:
            errors.append("CASE_SHA256_MISMATCH")

    return errors


# ---------------------------------------------------------------------------
# Epistemic Projection Contract Validator (Section D)
# ---------------------------------------------------------------------------

def _is_valid_projection_leaf_string(s: str, available_material_refs: Optional[Set[str]] = None) -> bool:
    """Return True if s is a valid leaf string in a projection matching allowed schemas/IDs/enums."""
    if not isinstance(s, str):
        return False
    if _SHA256_LEAF_RE.match(s) or _SCHEMA_LEAF_RE.match(s):
        return True
    if s in _PROJECTION_CLOSED_ENUMS:
        return True
    if available_material_refs and s in available_material_refs:
        return True
    if (_OBJECT_ID_RE.match(s) or _TARGET_NAME_RE.match(s) or _LINEAGE_ID_RE.match(s) or
            _CLAIM_ID_RE.match(s) or _CHECK_NAME_RE.match(s) or _WARNING_CODE_RE.match(s)):
        return True
    return False


def _scan_projection_forbidden(obj: Any, available_material_refs: Optional[Set[str]] = None, path: str = "") -> List[str]:
    """Recursively scan obj for forbidden keys and free-prose leaf strings."""
    errors: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            full_key = f"{path}.{k}" if path else k
            if k in PROJECTION_FORBIDDEN_KEYS:
                errors.append(f"PROJECTION_FORBIDDEN_KEY: {full_key}")
            errors.extend(_scan_projection_forbidden(v, available_material_refs, full_key))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            errors.extend(_scan_projection_forbidden(item, available_material_refs, f"{path}[{i}]"))
    elif isinstance(obj, str):
        if not _is_valid_projection_leaf_string(obj, available_material_refs):
            errors.append(f"PROJECTION_FREE_PROSE_LEAF: {path}={obj[:80]!r}")
    return errors


def validate_epistemic_projection(
    projection: Dict[str, Any],
    available_material_refs: Set[str],
) -> List[str]:
    """
    Strict epistemic projection validator (Section B).

    Returns a list of error codes. Empty list = valid.
    """
    errors: List[str] = []

    if not isinstance(projection, dict):
        errors.append("PROJECTION_NOT_DICT")
        return errors

    # --- Exact keys ---
    pkeys = set(projection.keys())
    missing_pk = PROJECTION_EXACT_KEYS - pkeys
    extra_pk = pkeys - PROJECTION_EXACT_KEYS
    if missing_pk:
        errors.append(f"PROJECTION_MISSING_KEYS: {sorted(missing_pk)}")
    if extra_pk:
        errors.append(f"PROJECTION_EXTRA_KEYS: {sorted(extra_pk)}")

    # --- Projection hash ---
    stored_psha = projection.get("projection_sha256", "")
    if not validate_sha256(stored_psha):
        errors.append(f"PROJECTION_SHA256_INVALID: {stored_psha!r}")
    else:
        body_without_sha = {k: v for k, v in projection.items() if k != "projection_sha256"}
        if "review_report" in body_without_sha and isinstance(body_without_sha["review_report"], dict):
            rr_copy = dict(body_without_sha["review_report"])
            rr_copy["projection_sha256"] = ""
            body_without_sha["review_report"] = rr_copy
        computed_psha = compute_canonical_sha256(body_without_sha)
        if computed_psha != stored_psha:
            errors.append("PROJECTION_SHA256_MISMATCH")

    # --- Recursive forbidden key and free-prose scan (excluding hash field) ---
    scan_target = {k: v for k, v in projection.items() if k != "projection_sha256"}
    errors.extend(_scan_projection_forbidden(scan_target, available_material_refs))

    # --- Object bindings ---
    for i, ob in enumerate(projection.get("object_bindings", [])):
        if not isinstance(ob, dict):
            errors.append(f"PROJECTION_OBJECT_BINDING_NOT_DICT[{i}]")
            continue
        ob_keys = set(ob.keys())
        if ob_keys != PROJECTION_OBJECT_BINDING_KEYS:
            missing_ob = PROJECTION_OBJECT_BINDING_KEYS - ob_keys
            extra_ob = ob_keys - PROJECTION_OBJECT_BINDING_KEYS
            if missing_ob:
                errors.append(f"PROJECTION_OB_MISSING_KEYS[{i}]: {sorted(missing_ob)}")
            if extra_ob:
                errors.append(f"PROJECTION_OB_EXTRA_KEYS[{i}]: {sorted(extra_ob)}")
        oid = ob.get("object_id")
        if not isinstance(oid, str) or not _OBJECT_ID_RE.match(oid):
            errors.append(f"PROJECTION_OB_OBJECT_ID_INVALID[{i}]: {oid!r}")
        tname = ob.get("target_name")
        if not isinstance(tname, str) or not _TARGET_NAME_RE.match(tname):
            errors.append(f"PROJECTION_OB_TARGET_NAME_INVALID[{i}]: {tname!r}")
        status = ob.get("status", "")
        if not isinstance(status, str) or status not in PROJECTION_OBJECT_BINDING_STATUS:
            errors.append(f"PROJECTION_OB_STATUS_INVALID[{i}]: {status!r}")
        ev = ob.get("evidence_refs", [])
        if not isinstance(ev, list):
            errors.append(f"PROJECTION_OB_EVIDENCE_NOT_LIST[{i}]")
        else:
            if len(ev) != len(set(ev)):
                errors.append(f"PROJECTION_OB_EVIDENCE_DUPLICATES[{i}]")
            for ref in ev:
                if not isinstance(ref, str) or ref not in available_material_refs:
                    errors.append(f"PROJECTION_OB_EVIDENCE_UNKNOWN[{i}]: {ref!r}")

    # --- Source lineage ---
    for i, sl in enumerate(projection.get("source_lineage", [])):
        if not isinstance(sl, dict):
            errors.append(f"PROJECTION_SOURCE_LINEAGE_NOT_DICT[{i}]")
            continue
        sl_keys = set(sl.keys())
        if sl_keys != PROJECTION_SOURCE_LINEAGE_KEYS:
            missing_sl = PROJECTION_SOURCE_LINEAGE_KEYS - sl_keys
            extra_sl = sl_keys - PROJECTION_SOURCE_LINEAGE_KEYS
            if missing_sl:
                errors.append(f"PROJECTION_SL_MISSING_KEYS[{i}]: {sorted(missing_sl)}")
            if extra_sl:
                errors.append(f"PROJECTION_SL_EXTRA_KEYS[{i}]: {sorted(extra_sl)}")
        lid = sl.get("lineage_id")
        if not isinstance(lid, str) or not _LINEAGE_ID_RE.match(lid):
            errors.append(f"PROJECTION_SL_LINEAGE_ID_INVALID[{i}]: {lid!r}")
        ind = sl.get("independence", "")
        if not isinstance(ind, str) or ind not in PROJECTION_LINEAGE_INDEPENDENCE:
            errors.append(f"PROJECTION_SL_INDEPENDENCE_INVALID[{i}]: {ind!r}")
        ev = sl.get("evidence_refs", [])
        if not isinstance(ev, list):
            errors.append(f"PROJECTION_SL_EVIDENCE_NOT_LIST[{i}]")
        else:
            if len(ev) != len(set(ev)):
                errors.append(f"PROJECTION_SL_EVIDENCE_DUPLICATES[{i}]")
            for ref in ev:
                if not isinstance(ref, str) or ref not in available_material_refs:
                    errors.append(f"PROJECTION_SL_EVIDENCE_UNKNOWN[{i}]: {ref!r}")

    # --- Extraction/Assessment separation ---
    for i, ea in enumerate(projection.get("extraction_assessment_separation", [])):
        if not isinstance(ea, dict):
            errors.append(f"PROJECTION_EA_NOT_DICT[{i}]")
            continue
        ea_keys = set(ea.keys())
        if ea_keys != PROJECTION_EXTRACTION_KEYS:
            missing_ea = PROJECTION_EXTRACTION_KEYS - ea_keys
            extra_ea = ea_keys - PROJECTION_EXTRACTION_KEYS
            if missing_ea:
                errors.append(f"PROJECTION_EA_MISSING_KEYS[{i}]: {sorted(missing_ea)}")
            if extra_ea:
                errors.append(f"PROJECTION_EA_EXTRA_KEYS[{i}]: {sorted(extra_ea)}")
        cid = ea.get("claim_id")
        if not isinstance(cid, str) or not _CLAIM_ID_RE.match(cid):
            errors.append(f"PROJECTION_EA_CLAIM_ID_INVALID[{i}]: {cid!r}")
        direction = ea.get("direction", "")
        if not isinstance(direction, str) or direction not in PROJECTION_DIRECTION:
            errors.append(f"PROJECTION_EA_DIRECTION_INVALID[{i}]: {direction!r}")
        ev = ea.get("evidence_refs", [])
        if not isinstance(ev, list):
            errors.append(f"PROJECTION_EA_EVIDENCE_NOT_LIST[{i}]")
        else:
            if len(ev) != len(set(ev)):
                errors.append(f"PROJECTION_EA_EVIDENCE_DUPLICATES[{i}]")
            for ref in ev:
                if not isinstance(ref, str) or ref not in available_material_refs:
                    errors.append(f"PROJECTION_EA_EVIDENCE_UNKNOWN[{i}]: {ref!r}")

    # --- Verification status ---
    for i, vs in enumerate(projection.get("verification_status", [])):
        if not isinstance(vs, dict):
            errors.append(f"PROJECTION_VS_NOT_DICT[{i}]")
            continue
        vs_keys = set(vs.keys())
        if vs_keys != PROJECTION_VERIFICATION_KEYS:
            missing_vs = PROJECTION_VERIFICATION_KEYS - vs_keys
            extra_vs = vs_keys - PROJECTION_VERIFICATION_KEYS
            if missing_vs:
                errors.append(f"PROJECTION_VS_MISSING_KEYS[{i}]: {sorted(missing_vs)}")
            if extra_vs:
                errors.append(f"PROJECTION_VS_EXTRA_KEYS[{i}]: {sorted(extra_vs)}")
        cname = vs.get("check_name")
        if not isinstance(cname, str) or not _CHECK_NAME_RE.match(cname):
            errors.append(f"PROJECTION_VS_CHECK_NAME_INVALID[{i}]: {cname!r}")
        status = vs.get("status", "")
        if not isinstance(status, str) or status not in PROJECTION_VERIFICATION_STATUS:
            errors.append(f"PROJECTION_VS_STATUS_INVALID[{i}]: {status!r}")
        ev = vs.get("evidence_refs", [])
        if not isinstance(ev, list):
            errors.append(f"PROJECTION_VS_EVIDENCE_NOT_LIST[{i}]")
        else:
            if len(ev) != len(set(ev)):
                errors.append(f"PROJECTION_VS_EVIDENCE_DUPLICATES[{i}]")
            for ref in ev:
                if not isinstance(ref, str) or ref not in available_material_refs:
                    errors.append(f"PROJECTION_VS_EVIDENCE_UNKNOWN[{i}]: {ref!r}")

    # --- Cannot-establish flags ---
    for i, ce in enumerate(projection.get("cannot_establish_flags", [])):
        if not isinstance(ce, dict):
            errors.append(f"PROJECTION_CE_NOT_DICT[{i}]")
            continue
        ce_keys = set(ce.keys())
        if ce_keys != PROJECTION_CANNOT_ESTABLISH_KEYS:
            missing_ce = PROJECTION_CANNOT_ESTABLISH_KEYS - ce_keys
            extra_ce = ce_keys - PROJECTION_CANNOT_ESTABLISH_KEYS
            if missing_ce:
                errors.append(f"PROJECTION_CE_MISSING_KEYS[{i}]: {sorted(missing_ce)}")
            if extra_ce:
                errors.append(f"PROJECTION_CE_EXTRA_KEYS[{i}]: {sorted(extra_ce)}")
        cid = ce.get("claim_id")
        if not isinstance(cid, str) or not _CLAIM_ID_RE.match(cid):
            errors.append(f"PROJECTION_CE_CLAIM_ID_INVALID[{i}]: {cid!r}")
        present = ce.get("present")
        if not isinstance(present, bool) or type(present) is not bool:
            errors.append(f"PROJECTION_CE_PRESENT_NOT_BOOL[{i}]: {present!r}")
        ev = ce.get("evidence_refs", [])
        if not isinstance(ev, list):
            errors.append(f"PROJECTION_CE_EVIDENCE_NOT_LIST[{i}]")
        else:
            if len(ev) != len(set(ev)):
                errors.append(f"PROJECTION_CE_EVIDENCE_DUPLICATES[{i}]")
            for ref in ev:
                if not isinstance(ref, str) or ref not in available_material_refs:
                    errors.append(f"PROJECTION_CE_EVIDENCE_UNKNOWN[{i}]: {ref!r}")

    # --- Conflicts ---
    for i, cf in enumerate(projection.get("conflicts", [])):
        if not isinstance(cf, dict):
            errors.append(f"PROJECTION_CF_NOT_DICT[{i}]")
            continue
        cf_keys = set(cf.keys())
        if cf_keys != PROJECTION_CONFLICT_KEYS:
            missing_cf = PROJECTION_CONFLICT_KEYS - cf_keys
            extra_cf = cf_keys - PROJECTION_CONFLICT_KEYS
            if missing_cf:
                errors.append(f"PROJECTION_CF_MISSING_KEYS[{i}]: {sorted(missing_cf)}")
            if extra_cf:
                errors.append(f"PROJECTION_CF_EXTRA_KEYS[{i}]: {sorted(extra_cf)}")
        cid = cf.get("claim_id")
        if not isinstance(cid, str) or not _CLAIM_ID_RE.match(cid):
            errors.append(f"PROJECTION_CF_CLAIM_ID_INVALID[{i}]: {cid!r}")
        present = cf.get("present")
        if not isinstance(present, bool) or type(present) is not bool:
            errors.append(f"PROJECTION_CF_PRESENT_NOT_BOOL[{i}]: {present!r}")
        ev = cf.get("evidence_refs", [])
        if not isinstance(ev, list):
            errors.append(f"PROJECTION_CF_EVIDENCE_NOT_LIST[{i}]")
        else:
            if len(ev) != len(set(ev)):
                errors.append(f"PROJECTION_CF_EVIDENCE_DUPLICATES[{i}]")
            for ref in ev:
                if not isinstance(ref, str) or ref not in available_material_refs:
                    errors.append(f"PROJECTION_CF_EVIDENCE_UNKNOWN[{i}]: {ref!r}")

    # --- Authority locks ---
    al = projection.get("authority_locks", {})
    if not isinstance(al, dict):
        errors.append("PROJECTION_AUTHORITY_LOCKS_NOT_DICT")
    else:
        al_keys = set(al.keys())
        missing_al = PROJECTION_AUTHORITY_LOCK_KEYS - al_keys
        extra_al = al_keys - PROJECTION_AUTHORITY_LOCK_KEYS
        if missing_al:
            errors.append(f"PROJECTION_AL_MISSING_KEYS: {sorted(missing_al)}")
        if extra_al:
            errors.append(f"PROJECTION_AL_EXTRA_KEYS: {sorted(extra_al)}")
        for ak in PROJECTION_AUTHORITY_LOCK_KEYS:
            if ak in al:
                val = al[ak]
                if type(val) is not bool:
                    errors.append(f"PROJECTION_AL_NOT_BOOL: {ak}={val!r}")
                elif val is not False:
                    errors.append(f"PROJECTION_AL_FLAG_MUST_BE_FALSE: {ak}={val!r}")

    # --- Review report ---
    rr = projection.get("review_report", {})
    if not isinstance(rr, dict):
        errors.append("PROJECTION_REVIEW_REPORT_NOT_DICT")
    else:
        rr_keys = set(rr.keys())
        missing_rr = PROJECTION_REVIEW_REPORT_KEYS - rr_keys
        extra_rr = rr_keys - PROJECTION_REVIEW_REPORT_KEYS
        if missing_rr:
            errors.append(f"PROJECTION_RR_MISSING_KEYS: {sorted(missing_rr)}")
        if extra_rr:
            errors.append(f"PROJECTION_RR_EXTRA_KEYS: {sorted(extra_rr)}")

        # Review report schema must be exact
        rr_schema = rr.get("schema")
        if rr_schema != PROJECTION_REVIEW_REPORT_SCHEMA:
            errors.append(f"PROJECTION_RR_SCHEMA_INVALID: {rr_schema!r}")

        # Review report projection_sha256 must match outer
        rr_psha = rr.get("projection_sha256", "")
        if validate_sha256(stored_psha) and rr_psha != stored_psha:
            errors.append(
                f"PROJECTION_RR_SHA256_MISMATCH: rr has {rr_psha[:8]!r} outer has {stored_psha[:8]!r}"
            )

        # object_count must be non-negative int, not bool
        oc = rr.get("object_count")
        if type(oc) is bool or isinstance(oc, bool):
            errors.append("PROJECTION_RR_OBJECT_COUNT_IS_BOOL")
        elif not isinstance(oc, int) or oc < 0:
            errors.append(f"PROJECTION_RR_OBJECT_COUNT_INVALID: {oc!r}")

        # warning_codes must be list[str]
        wc = rr.get("warning_codes", [])
        if not isinstance(wc, list):
            errors.append("PROJECTION_RR_WARNING_CODES_NOT_LIST")
        else:
            if len(wc) != len(set(wc)):
                errors.append("PROJECTION_RR_WARNING_CODES_DUPLICATE")
            for w in wc:
                if not isinstance(w, str) or not _WARNING_CODE_RE.match(w):
                    errors.append(f"PROJECTION_RR_WARNING_CODE_INVALID: {w!r}")

        # evidence_refs must be list[str]
        rr_ev = rr.get("evidence_refs", [])
        if not isinstance(rr_ev, list):
            errors.append("PROJECTION_RR_EVIDENCE_NOT_LIST")
        else:
            if len(rr_ev) != len(set(rr_ev)):
                errors.append("PROJECTION_RR_EVIDENCE_DUPLICATES")
            for ref in rr_ev:
                if not isinstance(ref, str) or ref not in available_material_refs:
                    errors.append(f"PROJECTION_RR_EVIDENCE_UNKNOWN: {ref!r}")

    return errors


# ---------------------------------------------------------------------------
# Oracle Contract
# ---------------------------------------------------------------------------

ORACLE_EXACT_KEYS: Set[str] = {
    "schema", "case_id", "oracle_class", "oracle_decision",
    "known_defects", "indeterminate_reason", "oracle_sha256",
}

ORACLE_DEFECT_KEYS: Set[str] = {
    "defect_id", "severity", "category", "description",
    "required_detection", "supporting_public_refs",
}


def validate_oracle_record(oracle: Dict[str, Any], case: Optional[Dict[str, Any]] = None) -> List[str]:
    errors: List[str] = []
    keys = set(oracle.keys())

    missing = ORACLE_EXACT_KEYS - keys
    extra = keys - ORACLE_EXACT_KEYS
    if missing:
        errors.append(f"ORACLE_MISSING_KEYS: {sorted(missing)}")
    if extra:
        errors.append(f"ORACLE_EXTRA_KEYS: {sorted(extra)}")

    # Enum validation
    oc = oracle.get("oracle_class", "")
    if oc not in {e.value for e in OracleClass}:
        errors.append(f"ORACLE_CLASS_INVALID: {oc!r}")
    od = oracle.get("oracle_decision", "")
    if od not in {e.value for e in BenchmarkDecision}:
        errors.append(f"ORACLE_DECISION_INVALID: {od!r}")

    # Consistency: CLEAN→ACCEPT, DEFECTIVE→REJECT, INDETERMINATE→BLOCK
    expected_decision = {
        "CLEAN": "ACCEPT",
        "DEFECTIVE": "REJECT",
        "INDETERMINATE": "BLOCK",
    }.get(oc)
    if expected_decision and od != expected_decision:
        errors.append(f"ORACLE_DECISION_INCONSISTENT: class={oc} decision={od} expected={expected_decision}")

    # Defects
    defects = oracle.get("known_defects", [])
    defect_ids: List[str] = []
    for d in defects:
        d_keys = set(d.keys())
        missing_d = ORACLE_DEFECT_KEYS - d_keys
        if missing_d:
            errors.append(f"ORACLE_DEFECT_MISSING_KEYS: {sorted(missing_d)}")
        severity = d.get("severity", "")
        if severity not in {e.value for e in DefectSeverity}:
            errors.append(f"ORACLE_DEFECT_SEVERITY_INVALID: {severity!r}")
        did = d.get("defect_id", "")
        if did:
            defect_ids.append(did)

        # Validate that supporting refs exist in public case
        if case is not None:
            case_refs = {m.get("ref") for m in case.get("materials", [])}
            case_refs |= set(case.get("available_evidence_refs", []))
            for ref in d.get("supporting_public_refs", []):
                if ref not in case_refs:
                    errors.append(f"ORACLE_REF_NOT_IN_CASE: {ref!r}")

    # No duplicate defect IDs within case
    if len(set(defect_ids)) != len(defect_ids):
        errors.append("ORACLE_DUPLICATE_DEFECT_IDS")

    # Oracle hash
    sha = oracle.get("oracle_sha256", "")
    if not validate_sha256(sha):
        errors.append(f"ORACLE_SHA256_INVALID: {sha!r}")
    else:
        body = {k: v for k, v in oracle.items() if k != "oracle_sha256"}
        expected = compute_canonical_sha256(body)
        if expected != sha:
            errors.append("ORACLE_SHA256_MISMATCH")

    return errors


# ---------------------------------------------------------------------------
# Packet Contract
# ---------------------------------------------------------------------------

PACKET_EXACT_KEYS: Set[str] = {
    "schema", "benchmark_run_id", "arm", "arm_protocol_version",
    "case_alias", "case_version", "common_materials",
    "common_materials_sha256", "arm_overlay", "response_contract",
    "packet_sha256",
}

PACKET_FORBIDDEN_KEYS: Set[str] = {
    "case_id", "oracle", "oracle_class", "oracle_decision", "known_defects",
    "expected_answer", "required_detection", "defect_ids", "oracle_sha256",
}


def validate_packet(packet: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    keys = set(packet.keys())

    missing = PACKET_EXACT_KEYS - keys
    extra = keys - PACKET_EXACT_KEYS
    if missing:
        errors.append(f"PACKET_MISSING_KEYS: {sorted(missing)}")
    if extra:
        errors.append(f"PACKET_EXTRA_KEYS: {sorted(extra)}")

    leaked = PACKET_FORBIDDEN_KEYS & keys
    if leaked:
        errors.append(f"PACKET_FORBIDDEN_KEYS: {sorted(leaked)}")

    arm = packet.get("arm", "")
    if arm not in {e.value for e in BenchmarkArm}:
        errors.append(f"PACKET_ARM_INVALID: {arm!r}")

    sha = packet.get("packet_sha256", "")
    if not validate_sha256(sha):
        errors.append(f"PACKET_SHA256_INVALID: {sha!r}")
    else:
        body = {k: v for k, v in packet.items() if k != "packet_sha256"}
        expected = compute_canonical_sha256(body)
        if expected != sha:
            errors.append("PACKET_SHA256_MISMATCH")

    return errors


# ---------------------------------------------------------------------------
# Observation Contract
# ---------------------------------------------------------------------------

OBSERVATION_EXACT_KEYS: Set[str] = {
    "schema", "observation_id", "benchmark_run_id", "arm", "case_alias",
    "packet_sha256", "evaluator", "decision", "detected_defect_ids", "cited_evidence_refs",
    "rationale_summary", "confidence", "execution",
    "skipped_checks", "observation_sha256",
}

OBSERVATION_EVALUATOR_KEYS: Set[str] = {
    "evaluator_id", "provider", "model_id", "prompt_version",
}

OBSERVATION_EXECUTION_KEYS: Set[str] = {
    "started_at", "completed_at", "duration_seconds",
    "input_tokens", "output_tokens", "cost_usd",
}

OBSERVATION_FORBIDDEN_KEYS: Set[str] = {
    "chain_of_thought", "full_cot", "reasoning_chain", "reasoning_steps",
    "oracle", "oracle_class", "oracle_decision", "expected_answer", "answer_key",
}

_ISO8601_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)


def _is_timezone_aware_iso8601(ts: str) -> bool:
    return bool(_ISO8601_RE.match(ts))


def _parse_timezone_aware_timestamp(ts: str) -> Optional[datetime]:
    """
    Parse a timezone-aware ISO-8601 timestamp into a datetime.

    Normalizes a trailing 'Z' to '+00:00' before parsing. Returns None when the
    string is not timezone-aware, when the calendar date is invalid, when the
    timezone offset is invalid, or when a leap second (seconds==60) is not
    representable — the caller must reject rather than guess.
    """
    if not isinstance(ts, str) or not _is_timezone_aware_iso8601(ts):
        return None
    normalized = ts[:-1] + "+00:00" if ts.endswith("Z") else ts
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _contains_forbidden_keys(obj: Any) -> Optional[str]:
    """Recursively scan data structures for any forbidden keys."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in OBSERVATION_FORBIDDEN_KEYS:
                return k
            found = _contains_forbidden_keys(v)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _contains_forbidden_keys(item)
            if found:
                return found
    return None


def validate_observation(obs: Dict[str, Any], packet: Optional[Dict[str, Any]] = None) -> List[str]:
    errors: List[str] = []
    if not isinstance(obs, dict):
        return ["OBS_NOT_DICT"]

    keys = set(obs.keys())

    missing = OBSERVATION_EXACT_KEYS - keys
    extra = keys - OBSERVATION_EXACT_KEYS
    if missing:
        errors.append(f"OBS_MISSING_KEYS: {sorted(missing)}")
    if extra:
        errors.append(f"OBS_EXTRA_KEYS: {sorted(extra)}")

    forbidden_key = _contains_forbidden_keys(obs)
    if forbidden_key:
        errors.append(f"OBS_FORBIDDEN_KEYS: {[forbidden_key]}")

    # Exact schema value (not just presence of the key)
    if obs.get("schema") != BENCHMARK_OBSERVATION_SCHEMA:
        errors.append(f"OBS_SCHEMA_INVALID: {obs.get('schema')!r}")

    # Identity fields must be exact non-empty strings (bool/int/null/list/dict are invalid)
    for id_field in ("observation_id", "benchmark_run_id", "case_alias", "schema"):
        val = obs.get(id_field)
        if not isinstance(val, str) or isinstance(val, bool) or not val:
            errors.append(f"OBS_IDENTITY_FIELD_INVALID: {id_field}={val!r}")

    # packet_sha256: 64-char lowercase hex
    pkt_sha = obs.get("packet_sha256")
    if not isinstance(pkt_sha, str) or not validate_sha256(pkt_sha):
        errors.append(f"OBS_PACKET_SHA256_INVALID: {pkt_sha!r}")

    # arm
    arm = obs.get("arm", "")
    if arm not in {e.value for e in BenchmarkArm}:
        errors.append(f"OBS_ARM_INVALID: {arm!r}")

    # decision
    decision = obs.get("decision", "")
    if decision not in {e.value for e in BenchmarkDecision}:
        errors.append(f"OBS_DECISION_INVALID: {decision!r}")

    # confidence: must be int 0–100, not bool
    conf = obs.get("confidence")
    if conf is not None:
        if isinstance(conf, bool):
            errors.append("OBS_CONFIDENCE_IS_BOOL")
        elif not isinstance(conf, int) or conf < 0 or conf > 100:
            errors.append(f"OBS_CONFIDENCE_INVALID: {conf!r}")

    # rationale summary: exact string <= 2000 chars
    rationale = obs.get("rationale_summary")
    if not isinstance(rationale, str):
        errors.append(f"OBS_RATIONALE_NOT_STRING: {type(rationale).__name__}")
    elif len(rationale) > 2000:
        errors.append("OBS_RATIONALE_TOO_LONG")

    # evaluator: exact keys, all exact non-empty string, no extra keys
    evaluator = obs.get("evaluator")
    if isinstance(evaluator, dict):
        ev_keys = set(evaluator.keys())
        missing_ev = OBSERVATION_EVALUATOR_KEYS - ev_keys
        extra_ev = ev_keys - OBSERVATION_EVALUATOR_KEYS
        if missing_ev:
            errors.append(f"OBS_EVALUATOR_MISSING_KEYS: {sorted(missing_ev)}")
        if extra_ev:
            errors.append(f"OBS_EVALUATOR_EXTRA_KEYS: {sorted(extra_ev)}")
        for ek in OBSERVATION_EVALUATOR_KEYS:
            val = evaluator.get(ek)
            if not isinstance(val, str) or isinstance(val, bool) or not val:
                errors.append(f"OBS_EVALUATOR_VALUE_INVALID: {ek}={val!r}")
    else:
        errors.append("OBS_EVALUATOR_NOT_DICT")

    # execution: exact keys, timestamps ISO-8601 aware, non-negative numbers, no extra keys
    execution = obs.get("execution")
    if isinstance(execution, dict):
        ex_keys = set(execution.keys())
        missing_ex = OBSERVATION_EXECUTION_KEYS - ex_keys
        extra_ex = ex_keys - OBSERVATION_EXECUTION_KEYS
        if missing_ex:
            errors.append(f"OBS_EXECUTION_MISSING_KEYS: {sorted(missing_ex)}")
        if extra_ex:
            errors.append(f"OBS_EXECUTION_EXTRA_KEYS: {sorted(extra_ex)}")

        dur = execution.get("duration_seconds")
        if dur is not None and (isinstance(dur, bool) or (not isinstance(dur, (int, float))) or dur < 0):
            errors.append(f"OBS_DURATION_NEGATIVE: {dur!r}")

        for tok_field in ("input_tokens", "output_tokens"):
            tok = execution.get(tok_field)
            if tok is not None and (not isinstance(tok, int) or isinstance(tok, bool) or tok < 0):
                errors.append(f"OBS_TOKENS_INVALID: {tok_field}={tok!r}")

        cost = execution.get("cost_usd")
        if cost is not None and (isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0):
            errors.append(f"OBS_COST_NEGATIVE: {cost!r}")

        start_ts = execution.get("started_at", "")
        comp_ts = execution.get("completed_at", "")
        start_dt = None
        comp_dt = None
        for ts_name, ts_val in (("started_at", start_ts), ("completed_at", comp_ts)):
            if not isinstance(ts_val, str) or not _is_timezone_aware_iso8601(ts_val):
                errors.append(f"OBS_TIMESTAMP_NOT_AWARE: {ts_name}={ts_val!r}")
                continue
            dt = _parse_timezone_aware_timestamp(ts_val)
            if dt is None:
                errors.append(f"OBS_TIMESTAMP_INVALID: {ts_name}={ts_val!r}")
                continue
            if ts_name == "started_at":
                start_dt = dt
            else:
                comp_dt = dt
        # Compare actual instants, never raw strings.
        if start_dt is not None and comp_dt is not None and comp_dt < start_dt:
            errors.append(f"OBS_COMPLETED_BEFORE_STARTED: completed={comp_ts!r} started={start_ts!r}")
    else:
        errors.append("OBS_EXECUTION_NOT_DICT")

    # List fields: list[str] and no duplicates
    for list_field in ("detected_defect_ids", "cited_evidence_refs", "skipped_checks"):
        val_list = obs.get(list_field)
        if not isinstance(val_list, list):
            errors.append(f"OBS_LIST_NOT_LIST: {list_field}={type(val_list).__name__}")
        else:
            for item in val_list:
                if not isinstance(item, str) or isinstance(item, bool):
                    errors.append(f"OBS_LIST_ITEM_NOT_STRING: {list_field}={item!r}")
            if len(val_list) != len(set(val_list)):
                errors.append(f"OBS_LIST_DUPLICATE_ITEMS: {list_field}")

    # cited evidence refs must exist in packet
    cited_refs = obs.get("cited_evidence_refs", [])
    if packet is not None and isinstance(cited_refs, list):
        packet_refs = set()
        for m in packet.get("common_materials", {}).get("materials", []):
            packet_refs.add(m.get("ref", ""))
        for ref in packet.get("common_materials", {}).get("available_evidence_refs", []):
            packet_refs.add(ref)
        for ref in cited_refs:
            if isinstance(ref, str) and ref and ref not in packet_refs:
                errors.append(f"OBS_CITED_REF_NOT_IN_PACKET: {ref!r}")

    # observation hash
    sha = obs.get("observation_sha256", "")
    if not isinstance(sha, str) or not validate_sha256(sha):
        errors.append(f"OBS_SHA256_INVALID: {sha!r}")
    else:
        body = {k: v for k, v in obs.items() if k != "observation_sha256"}
        expected = compute_canonical_sha256(body)
        if expected != sha:
            errors.append("OBS_SHA256_MISMATCH")

    return errors


# ---------------------------------------------------------------------------
# Report Contract
# ---------------------------------------------------------------------------

REPORT_EXACT_KEYS: Set[str] = {
    "schema", "benchmark_run", "corpus", "coverage", "arms",
    "comparisons", "limitations", "claim_ceiling", "report_sha256",
}

CLAIM_CEILING_TEXT = (
    "This benchmark report summarizes observations collected under versioned "
    "synthetic review protocols. It does not establish statistical significance, "
    "general research-quality improvement, production readiness, or that an "
    "epistemic ledger is necessary."
)

REQUIRED_LIMITATIONS: Tuple[str, ...] = (
    "synthetic corpus",
    "no live model calls performed by harness",
    "model/provider results depend on imported observations",
    "local repository access can defeat oracle isolation if packet boundaries are ignored",
    "small corpus",
    "no external validity claim",
    "no regulated-domain claim",
)

FORBIDDEN_REPORT_WORDS: Tuple[str, ...] = (
    "winner",
    "proven better",
    "statistically significant",
    "production ready",
    "arm c wins",
    "ledger proven",
    "research improved",
)

validate_case = validate_public_case
validate_oracle = validate_oracle_record
