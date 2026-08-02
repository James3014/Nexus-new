"""
Deterministic Epistemic Review Report (nexus.epistemic_review_report.v1).

Builds a structured, deterministic report from a verified epistemic export.
This module is strictly read-only: it never modifies source exports, receipts,
or any runtime state.

Report ceiling (immutable):
  This report summarizes verified evidence structure and limitations. It does
  not establish truth, approve integration, unlock public claims, or indicate
  production readiness.
"""

import hashlib
import json
import os
import uuid
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from nexus.research.epistemic_profile.adapter import (
    build_epistemic_receipt_extension,
    build_epistemic_verification_result,
)
from nexus.research.epistemic_profile.contracts import (
    EpistemicIntegrityStatus,
    EpistemicProfileInput,
)
from nexus.research.epistemic_profile.io import (
    load_epistemic_profile_export,
    verify_epistemic_profile_export,
)

REPORT_SCHEMA = "nexus.epistemic_review_report.v1"

REPORT_CEILING = (
    "This report summarizes verified evidence structure and limitations. "
    "It does not establish truth, approve integration, unlock public claims, "
    "or indicate production readiness."
)

REPORT_TOP_LEVEL_KEYS: Set[str] = {
    "schema",
    "source",
    "verification_status",
    "records_checked",
    "claim_count",
    "artifact_count",
    "global_summary",
    "claims",
    "authority",
    "report_sha256",
}

FORBIDDEN_REPORT_CONTENT: Tuple[str, ...] = (
    "original_text",
    "user_position",
    "salt",
    "sealed",
    "can_establish",
    "cannot_establish",
    "reasoning_steps",
    "chain_of_thought",
    "api_key",
    "secret",
    "password",
    "positions.sqlite3",
)

FORBIDDEN_AUTHORITY_VALUES: Tuple[str, ...] = (
    "ACCEPTED",
    "PROVEN",
    "TRUE",
    "FINAL",
    "PRODUCTION_READY",
)


def _canonical_json(obj: Any) -> str:
    """Deterministic JSON serialization (sorted keys, no spaces)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _format_coverage(numerator: int, denominator: int) -> str:
    """Return 4-decimal-place coverage string, e.g. '1.0000'."""
    if denominator == 0:
        return "0.0000"
    val = Decimal(numerator) / Decimal(denominator)
    return f"{val:.4f}"


def _scan_forbidden(obj: Any, path: str = "") -> List[str]:
    """Return list of forbidden field paths found in the nested object."""
    hits: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_lower = k.lower()
            for forbidden in FORBIDDEN_REPORT_CONTENT:
                if forbidden in key_lower:
                    hits.append(f"{path}.{k}" if path else k)
                    break
            hits.extend(_scan_forbidden(v, f"{path}.{k}" if path else k))
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            hits.extend(_scan_forbidden(item, f"{path}[{i}]"))
    elif isinstance(obj, str):
        val_lower = obj.lower()
        for forbidden in FORBIDDEN_REPORT_CONTENT:
            if forbidden in val_lower:
                hits.append(f"{path}=<redacted>")
                break
        for bad_val in FORBIDDEN_AUTHORITY_VALUES:
            if bad_val in obj.upper():
                hits.append(f"{path}=<forbidden_status>")
                break
    return hits


def build_epistemic_review_report(
    source_export: Union[str, Path, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build a deterministic Epistemic Review Report from a verified export.

    The export MUST pass strict validation (PASS status). Raises ValueError
    with code EP_REPORT_REQUIRES_VERIFIED_EXPORT if it does not.

    Returns the report dict including report_sha256. Does NOT write any file.
    """
    # 1. Strict load + verify (single non-bypassable path)
    ver = verify_epistemic_profile_export(source_export)
    if ver.status != EpistemicIntegrityStatus.PASS:
        raise ValueError(
            f"EP_REPORT_REQUIRES_VERIFIED_EXPORT: export verification status is "
            f"{ver.status.value}, blockers: {list(ver.blockers)}"
        )

    # 2. Load the validated input (re-uses same parser path)
    inp = load_epistemic_profile_export(source_export)

    # 3. Build receipt extension via ClaimBoundary (authority source)
    receipt_ext = build_epistemic_receipt_extension(inp)
    boundary_dict = (
        receipt_ext.claim_boundary.to_dict()
        if receipt_ext.claim_boundary and hasattr(receipt_ext.claim_boundary, "to_dict")
        else {}
    )

    # 4. Extract source metadata from verification result
    source_section = {
        "export_schema": ver.source_schema,
        "export_id": ver.source_export_id,
        "export_sha256": ver.source_export_sha256,
        "state_manifest_sha256": ver.source_state_manifest_sha256,
        "task_id": ver.source_task_id,
        "attempt_id": ver.source_attempt_id,
        "profile_id": ver.source_profile_id,
        "run_id": ver.source_run_id,
    }

    # 5. Build per-claim summaries (sorted by claim_id for determinism)
    records = inp.records
    claims_map: Dict[str, Dict[str, Any]] = {}
    all_artifact_ids: Set[str] = set()

    direction_counts: Dict[str, int] = {
        "supports": 0, "contradicts": 0, "contextual": 0,
        "inconclusive": 0, "unknown": 0,
    }
    scope_counts: Dict[str, int] = {
        "matched": 0, "partial": 0, "mismatched": 0, "unknown": 0,
    }
    lineage_counts: Dict[str, int] = {
        "independent": 0, "derivative": 0, "shared_origin": 0, "unknown": 0,
    }

    supports_contradicts_total = 0
    cannot_est_true_in_sc = 0

    all_evidence_refs: Set[str] = set()
    all_receipt_refs: Set[str] = set()
    conflicting_claim_ids: Set[str] = set()

    for rec in records:
        cid = rec.claim_id
        if cid not in claims_map:
            claims_map[cid] = {
                "claim_id": cid,
                "record_count": 0,
                "artifact_ids": set(),
                "directions": defaultdict(int),
                "scope_alignment": defaultdict(int),
                "lineage_independence": defaultdict(int),
                "evidence_refs": [],
                "receipt_refs": [],
                "blockers": [],
                "cannot_establish_total": 0,
                "sc_total": 0,
            }

        cm = claims_map[cid]
        cm["record_count"] += 1

        # direction
        dir_val = rec.direction.value if hasattr(rec.direction, "value") else str(rec.direction)
        cm["directions"][dir_val] += 1
        if dir_val in direction_counts:
            direction_counts[dir_val] += 1
        else:
            direction_counts["unknown"] += 1

        # scope_alignment
        scope_val = rec.scope_alignment.value if hasattr(rec.scope_alignment, "value") else str(rec.scope_alignment)
        cm["scope_alignment"][scope_val] += 1
        if scope_val in scope_counts:
            scope_counts[scope_val] += 1
        else:
            scope_counts["unknown"] += 1

        # artifact
        art_id = rec.artifact.artifact_id if rec.artifact else None
        if art_id:
            cm["artifact_ids"].add(art_id)
            all_artifact_ids.add(art_id)

        # lineage independence
        lin_val = rec.artifact.lineage_independence if rec.artifact else "unknown"
        if lin_val not in lineage_counts:
            lin_val = "unknown"
        cm["lineage_independence"][lin_val] += 1
        lineage_counts[lin_val] += 1

        # cannot_establish coverage
        if dir_val in ("supports", "contradicts"):
            cm["sc_total"] += 1
            supports_contradicts_total += 1
            if rec.cannot_establish_present:
                cm["cannot_establish_total"] += 1
                cannot_est_true_in_sc += 1

        # evidence and receipt refs
        ext_ref = rec.extraction_ref
        if ext_ref:
            cm["evidence_refs"].append(ext_ref)
            all_evidence_refs.add(ext_ref)
        for rr in rec.receipt_refs:
            cm["receipt_refs"].append(rr)
            all_receipt_refs.add(rr)

        # blockers
        for bl in rec.blockers:
            cm["blockers"].append(bl)

    # Detect conflicts (claim has both supports AND contradicts records)
    for cid, cm in claims_map.items():
        if cm["directions"].get("supports", 0) > 0 and cm["directions"].get("contradicts", 0) > 0:
            conflicting_claim_ids.add(cid)

    # Build sorted claims list
    claims_list = []
    for cid in sorted(claims_map.keys()):
        cm = claims_map[cid]
        cannot_est_cov = _format_coverage(cm["cannot_establish_total"], cm["sc_total"])
        claims_list.append({
            "claim_id": cid,
            "record_count": cm["record_count"],
            "artifact_count": len(cm["artifact_ids"]),
            "directions": dict(cm["directions"]),
            "scope_alignment": dict(cm["scope_alignment"]),
            "lineage_independence": dict(cm["lineage_independence"]),
            "conflict_present": cid in conflicting_claim_ids,
            "cannot_establish_coverage": cannot_est_cov,
            "evidence_refs": sorted(set(cm["evidence_refs"])),
            "receipt_refs": sorted(set(cm["receipt_refs"])),
            "blockers": list(dict.fromkeys(cm["blockers"])),
        })

    global_cannot_est_cov = _format_coverage(cannot_est_true_in_sc, supports_contradicts_total)

    global_summary = {
        "directions": direction_counts,
        "scope_alignment": scope_counts,
        "lineage_independence": lineage_counts,
        "conflicting_claim_count": len(conflicting_claim_ids),
        "cannot_establish_coverage": global_cannot_est_cov,
        "unique_evidence_ref_count": len(all_evidence_refs),
        "unique_receipt_ref_count": len(all_receipt_refs),
    }

    # Authority from ClaimBoundary (read-only; all flags are false)
    authority = {
        "runtime_update_allowed": bool(boundary_dict.get("runtime_update_allowed", False)),
        "public_claim_allowed": bool(boundary_dict.get("public_claim_allowed", False)),
        "public_benchmark_allowed": bool(boundary_dict.get("public_benchmark_allowed", False)),
        "production_ready": bool(boundary_dict.get("production_ready", False)),
        "integration_approved": bool(boundary_dict.get("integration_approved", False)),
    }
    # Enforce: none of these may ever be true
    for k in authority:
        authority[k] = False

    report_body: Dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "source": source_section,
        "verification_status": ver.status.value,
        "records_checked": len(records),
        "claim_count": len(claims_map),
        "artifact_count": len(all_artifact_ids),
        "global_summary": global_summary,
        "claims": claims_list,
        "authority": authority,
    }

    # 6. Compute deterministic hash over body (excluding report_sha256)
    canonical = _canonical_json(report_body)
    report_sha256 = _sha256(canonical)
    report_body["report_sha256"] = report_sha256

    return report_body


def render_epistemic_review_markdown(report: Dict[str, Any]) -> str:
    """
    Render a deterministic Markdown summary of the Epistemic Review Report.
    Does NOT embed raw JSON or the full export content.
    """
    lines: List[str] = []

    schema = report.get("schema", "")
    src = report.get("source", {})
    ver_status = report.get("verification_status", "")
    records_checked = report.get("records_checked", 0)
    claim_count = report.get("claim_count", 0)
    artifact_count = report.get("artifact_count", 0)
    g = report.get("global_summary", {})
    auth = report.get("authority", {})
    report_sha = report.get("report_sha256", "")

    lines.append("# Epistemic Review Report")
    lines.append("")
    lines.append(f"**Schema**: `{schema}`")
    lines.append(f"**Report SHA-256**: `{report_sha}`")
    lines.append("")

    lines.append("## Source Export")
    lines.append("")
    lines.append(f"- Export ID: `{src.get('export_id', '')}`")
    lines.append(f"- Export SHA-256: `{src.get('export_sha256', '')}`")
    lines.append(f"- State Manifest SHA-256: `{src.get('state_manifest_sha256', '')}`")
    lines.append(f"- Task ID: `{src.get('task_id', '')}`")
    lines.append(f"- Attempt ID: `{src.get('attempt_id', '')}`")
    lines.append(f"- Profile ID: `{src.get('profile_id', '')}`")
    lines.append(f"- Run ID: `{src.get('run_id', '')}`")
    lines.append("")

    lines.append("## Verification Status")
    lines.append("")
    lines.append(f"**Status**: `{ver_status}`")
    lines.append(f"- Records checked: {records_checked}")
    lines.append(f"- Claims: {claim_count}")
    lines.append(f"- Artifacts: {artifact_count}")
    lines.append("")

    lines.append("## Global Evidence Summary")
    lines.append("")
    dir_counts = g.get("directions", {})
    lines.append("### Directions")
    lines.append("")
    for d in ("supports", "contradicts", "contextual", "inconclusive", "unknown"):
        lines.append(f"- {d}: {dir_counts.get(d, 0)}")
    lines.append("")

    scope_counts = g.get("scope_alignment", {})
    lines.append("### Scope Alignment")
    lines.append("")
    for s in ("matched", "partial", "mismatched", "unknown"):
        lines.append(f"- {s}: {scope_counts.get(s, 0)}")
    lines.append("")

    lin_counts = g.get("lineage_independence", {})
    lines.append("### Lineage Independence")
    lines.append("")
    for li in ("independent", "derivative", "shared_origin", "unknown"):
        lines.append(f"- {li}: {lin_counts.get(li, 0)}")
    lines.append("")

    lines.append("## Conflicts")
    lines.append("")
    conflict_count = g.get("conflicting_claim_count", 0)
    if conflict_count > 0:
        lines.append(
            f"**{conflict_count} claim(s)** have both `supports` and `contradicts` records."
        )
    else:
        lines.append("No conflicting claims detected.")
    lines.append("")

    lines.append("## Cannot-Establish Coverage")
    lines.append("")
    cov = g.get("cannot_establish_coverage", "0.0000")
    lines.append(
        f"Coverage (supports/contradicts records with cannot_establish_present=true): **{cov}**"
    )
    lines.append("")

    lines.append("## Claim-by-Claim Summary")
    lines.append("")
    claims = report.get("claims", [])
    for claim in claims:
        cid = claim.get("claim_id", "")
        lines.append(f"### Claim `{cid}`")
        lines.append("")
        lines.append(f"- Records: {claim.get('record_count', 0)}")
        lines.append(f"- Artifacts: {claim.get('artifact_count', 0)}")
        lines.append(f"- Conflict present: {claim.get('conflict_present', False)}")
        lines.append(f"- Cannot-establish coverage: {claim.get('cannot_establish_coverage', '0.0000')}")
        dirs = claim.get("directions", {})
        lines.append(f"- Directions: {dirs}")
        blockers = claim.get("blockers", [])
        if blockers:
            lines.append(f"- Blockers: {blockers}")
        lines.append("")

    lines.append("## Authority Locks")
    lines.append("")
    lines.append("| Permission | Status |")
    lines.append("|---|---|")
    for k, v in auth.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")

    lines.append("## Claim Ceiling")
    lines.append("")
    lines.append(f"> {REPORT_CEILING}")
    lines.append("")

    return "\n".join(lines)


def verify_epistemic_review_report(
    report: Dict[str, Any],
    source_export: Union[str, Path, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Verify an Epistemic Review Report against its source export.

    Read-only: does NOT modify report or source export.

    Returns dict with status REVIEW_VERIFIED or REVIEW_INVALID + blockers.
    """
    blockers: List[str] = []

    # 1. Check report keys
    report_keys = set(report.keys()) if isinstance(report, dict) else set()
    if report_keys != REPORT_TOP_LEVEL_KEYS:
        missing = REPORT_TOP_LEVEL_KEYS - report_keys
        extra = report_keys - REPORT_TOP_LEVEL_KEYS
        if missing:
            blockers.append(f"REPORT_MISSING_KEYS: {sorted(missing)}")
        if extra:
            blockers.append(f"REPORT_EXTRA_KEYS: {sorted(extra)}")

    # 2. Verify source export (read-only)
    try:
        ver = verify_epistemic_profile_export(source_export)
    except Exception as e:
        blockers.append(f"REPORT_SOURCE_VERIFY_FAILED: {e}")
        return {
            "status": "REVIEW_INVALID",
            "blockers": blockers,
            "report_sha256": report.get("report_sha256", ""),
        }

    if ver.status != EpistemicIntegrityStatus.PASS:
        blockers.append(
            f"REPORT_SOURCE_NOT_VERIFIED: status={ver.status.value}, blockers={list(ver.blockers)}"
        )

    # 3. Rebuild expected report (deterministic)
    try:
        expected = build_epistemic_review_report(source_export)
    except Exception as e:
        blockers.append(f"REPORT_REBUILD_FAILED: {e}")
        return {
            "status": "REVIEW_INVALID",
            "blockers": blockers,
            "report_sha256": report.get("report_sha256", ""),
        }

    # 4. Verify report hash
    provided_hash = report.get("report_sha256", "")
    expected_hash = expected.get("report_sha256", "")

    if provided_hash != expected_hash:
        blockers.append(
            f"REPORT_HASH_MISMATCH: provided={provided_hash!r} expected={expected_hash!r}"
        )

    # 5. Semantic field comparison (detects count tampering + hash recompute forgery)
    _compare_fields(report, expected, blockers, path="")

    # 6. Source export binding check
    rep_src = report.get("source", {})
    exp_src = expected.get("source", {})
    for field in ("export_id", "export_sha256", "state_manifest_sha256",
                  "task_id", "attempt_id", "profile_id", "run_id"):
        if rep_src.get(field) != exp_src.get(field):
            blockers.append(
                f"REPORT_SOURCE_BINDING_MISMATCH: field={field} "
                f"provided={rep_src.get(field)!r} expected={exp_src.get(field)!r}"
            )

    if blockers:
        return {
            "status": "REVIEW_INVALID",
            "blockers": blockers,
            "report_sha256": provided_hash,
        }

    return {
        "status": "REVIEW_VERIFIED",
        "blockers": [],
        "report_sha256": expected_hash,
        "source_export_id": ver.source_export_id,
        "source_export_sha256": ver.source_export_sha256,
    }


def _compare_fields(
    actual: Any, expected: Any, blockers: List[str], path: str
) -> None:
    """Recursively compare report fields; ignore report_sha256 (checked separately)."""
    if path.endswith(".report_sha256") or path == "report_sha256":
        return
    if type(actual) != type(expected):
        blockers.append(
            f"REPORT_FIELD_TYPE_MISMATCH: {path} "
            f"type={type(actual).__name__} expected={type(expected).__name__}"
        )
        return
    if isinstance(actual, dict):
        all_keys = set(actual.keys()) | set(expected.keys())
        for k in all_keys:
            _compare_fields(
                actual.get(k), expected.get(k), blockers,
                f"{path}.{k}" if path else k,
            )
    elif isinstance(actual, list):
        if len(actual) != len(expected):
            blockers.append(
                f"REPORT_LIST_LENGTH_MISMATCH: {path} "
                f"len={len(actual)} expected={len(expected)}"
            )
        else:
            for i, (a, e) in enumerate(zip(actual, expected)):
                _compare_fields(a, e, blockers, f"{path}[{i}]")
    else:
        if actual != expected:
            blockers.append(
                f"REPORT_FIELD_MISMATCH: {path} "
                f"value={actual!r} expected={expected!r}"
            )


def write_epistemic_review_report(
    source_export: Union[str, Path, Dict[str, Any]],
    json_output_path: Union[str, Path],
    markdown_output_path: Union[str, Path],
) -> Dict[str, Any]:
    """
    Build and atomically write the Epistemic Review Report (JSON + Markdown).

    All-or-nothing: if either write fails, existing outputs are not modified.
    Returns the report dict.
    """
    json_out = Path(json_output_path).resolve()
    md_out = Path(markdown_output_path).resolve()

    # Build first (may raise)
    report = build_epistemic_review_report(source_export)
    md = render_epistemic_review_markdown(report)

    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)

    uid = uuid.uuid4().hex[:12]
    tmp_json = json_out.parent / f".tmp_report_{uid}_json.json"
    tmp_md = md_out.parent / f".tmp_report_{uid}_md.md"

    # Track existing content for rollback
    existing_json: Optional[bytes] = None
    existing_md: Optional[bytes] = None
    if json_out.exists():
        existing_json = json_out.read_bytes()
    if md_out.exists():
        existing_md = md_out.read_bytes()

    try:
        # Write temp files with fsync
        with open(tmp_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        with open(tmp_md, "w", encoding="utf-8") as f:
            f.write(md)
            f.flush()
            os.fsync(f.fileno())

        # Atomic replace both
        os.replace(tmp_json, json_out)
        os.replace(tmp_md, md_out)

    except Exception as exc:
        # Cleanup temp files
        for tp in (tmp_json, tmp_md):
            if tp.exists():
                try:
                    tp.unlink()
                except OSError:
                    pass

        # Restore existing outputs if they were partially overwritten
        # (os.replace is atomic per POSIX, so this only matters for the second replace)
        if existing_json is not None and json_out.exists():
            try:
                json_out.write_bytes(existing_json)
            except OSError:
                pass
        if existing_md is not None and md_out.exists():
            try:
                md_out.write_bytes(existing_md)
            except OSError:
                pass

        raise exc

    return report
