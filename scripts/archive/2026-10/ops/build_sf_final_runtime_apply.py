#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_CURRENT_OVERLAY = Path("docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_2026-05-20.json")
DEFAULT_LIVE_REPORT = Path("docs/reports/NEXUS_SF_FINAL_ALL_CANDIDATE_LIVE_COMPARE_REPORT_2026-05-21.json")
DEFAULT_FINAL_STATUS = Path("docs/reports/NEXUS_SF_FINAL_ALL_CANDIDATE_LIVE_COMPARE_SKILL_STATUS_2026-05-21.json")
DEFAULT_CURRENT_STATUS = Path("docs/reports/NEXUS_SF_SYSTEMATIC_BATCH_SKILL_STATUS_2026-05-19.json")
DEFAULT_CATALOG_VERDICTS = Path("docs/reports/NEXUS_SKILL_FIT_CATALOG_REPAIR_AND_CODING_2026-05-15.json")
DEFAULT_DECISION = Path("docs/reports/NEXUS_SF_FINAL_RUNTIME_APPLY_DECISION_2026-05-21.json")
DEFAULT_OVERLAY = Path("docs/reports/NEXUS_SF_FINAL_RUNTIME_SKILL_POLICY_OVERLAY_APPLIED_2026-05-21.json")
DEFAULT_STATUS = Path("docs/reports/NEXUS_SF_FINAL_RUNTIME_SKILL_STATUS_MERGED_2026-05-21.json")
SECURITY_CONTRACT_VERSION = "v1_diagnostic_only"
PROMOTION_CREDIT_SOURCE = "none"


def _is_clean_replacement(row: Mapping[str, Any]) -> bool:
    candidate = row.get("candidate") if isinstance(row.get("candidate"), Mapping) else {}
    delta = row.get("delta") if isinstance(row.get("delta"), Mapping) else {}
    return bool(
        row.get("verdict") == "REPLACE_PRIMARY_LIVE_APPROVED"
        and candidate.get("status") == "PASS"
        and candidate.get("delivery_status") == "SUCCESS"
        and candidate.get("receipt_chain_pass") is True
        and candidate.get("trust_mismatch") is False
        and candidate.get("skill_mount_contract_status") == "PASS"
        and str(candidate.get("infra_invalid_reason") or "") == ""
        and isinstance(delta.get("token_delta"), (int, float))
        and isinstance(delta.get("wall_delta"), (int, float))
        and delta["token_delta"] < 0
        and delta["wall_delta"] < 0
    )


def _best_replacement_by_capability(live_report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in live_report.get("comparisons", []) or []:
        if not isinstance(row, Mapping) or not _is_clean_replacement(row):
            continue
        capability = str(row.get("capability") or "")
        if capability:
            grouped.setdefault(capability, []).append(row)
    return {
        capability: min(
            rows,
            key=lambda row: (
                float((row.get("delta") or {}).get("token_delta") or 0),
                float((row.get("delta") or {}).get("wall_delta") or 0),
                str(row.get("candidate_skill_id") or ""),
            ),
        )
        for capability, rows in grouped.items()
    }


def _status_rows_by_skill(*reports: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for report in reports:
        for raw in report.get("skills", []) or []:
            if not isinstance(raw, Mapping):
                continue
            name = str(raw.get("name") or raw.get("dir_name") or "")
            if not name:
                continue
            row = dict(raw)
            if name not in rows or str(row.get("test_level") or "") >= str(rows[name].get("test_level") or ""):
                rows[name] = row
    return rows


def _reject_verdicts_by_skill(report: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for raw in report.get("skill_verdicts", []) or []:
        if not isinstance(raw, Mapping):
            continue
        skill_id = str(raw.get("skill_id") or "")
        if not skill_id:
            continue
        if raw.get("verdict") == "reject" or raw.get("runtime_eligible") is False:
            rows.setdefault(skill_id, []).append(dict(raw))
    return rows


def _requires_curation(source: Mapping[str, Any]) -> bool:
    return str(source.get("skill_status") or "") != "nexus_curated_candidate"


def _runtime_status_row(*, skill_id: str, capability: str, source: Mapping[str, Any]) -> dict[str, Any]:
    requires_curation = _requires_curation(source)
    return {
        **dict(source),
        "name": skill_id,
        "test_level": "sf_final_runtime_apply_reviewed",
        "action": "runtime_policy_overlay_only",
        "capability_mount": capability,
        "family": capability,
        "requires_curation": requires_curation,
        "runtime_review_scope": "overlay_only_requires_curation" if requires_curation else "overlay_only_curated",
        "security_contract_version": SECURITY_CONTRACT_VERSION,
        "promotion_credit_source": PROMOTION_CREDIT_SOURCE,
        "v1_evidence_count": 1,
        "v2_evidence_count": 0,
        "v2_trust_mismatch_count": 0,
        "requires_sandbox_attestation": True,
        "sandbox_attestation_status": "missing_not_required_for_overlay_only",
        "v2_promotion_eligible": False,
        "reason_codes": sorted(
            set([*(str(item) for item in source.get("reason_codes", []) or []), "sf_final_runtime_apply"])
        ),
    }


def build_sf_final_runtime_apply(
    *,
    current_overlay: Mapping[str, Any],
    live_report: Mapping[str, Any],
    status_reports: list[Mapping[str, Any]],
    catalog_verdict_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    reject_conflict_warnings: list[dict[str, Any]] = []
    if current_overlay.get("status") != "PASS":
        blockers.append("current_overlay_not_pass")
    summary = live_report.get("summary") if isinstance(live_report.get("summary"), Mapping) else {}
    if int(summary.get("pending_candidate_count", -1)) != 0:
        blockers.append("live_report_has_pending_candidates")
    if int(summary.get("comparison_count") or 0) != int(summary.get("expected_candidate_count") or -1):
        blockers.append("live_report_incomplete_comparison_count")

    primary = dict(current_overlay.get("primary_skill_by_capability") or {})
    if not primary:
        blockers.append("current_overlay_missing_primary_map")
    replacements = _best_replacement_by_capability(live_report)
    status_by_skill = _status_rows_by_skill(*status_reports)
    rejected_by_skill = _reject_verdicts_by_skill(catalog_verdict_report or {})
    applied: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    runtime_status_rows: dict[str, dict[str, Any]] = {}

    for capability, old_skill in sorted((str(k), str(v)) for k, v in primary.items()):
        winner = replacements.get(capability)
        if winner:
            skill_id = str(winner.get("candidate_skill_id") or "")
            evidence = winner.get("candidate") if isinstance(winner.get("candidate"), Mapping) else {}
            source = status_by_skill.get(skill_id)
            if not source:
                blockers.append(f"{capability}:{skill_id}:missing_skill_status")
                continue
            requires_curation = _requires_curation(source)
            conflict_rows = rejected_by_skill.get(skill_id, [])
            same_capability_conflicts = [
                row for row in conflict_rows if str(row.get("capability") or "") == capability
            ]
            if same_capability_conflicts:
                blockers.append(f"{capability}:{skill_id}:same_capability_reject_conflict")
                continue
            for row in conflict_rows:
                reject_capability = str(row.get("capability") or "")
                reject_conflict_warnings.append(
                    {
                        "capability_id": capability,
                        "skill_id": skill_id,
                        "reject_capability": reject_capability,
                        "reject_verdict": str(row.get("verdict") or ""),
                        "reject_runtime_eligible": row.get("runtime_eligible"),
                        "reason": "cross_capability_reject_conflict",
                    }
                )
            primary[capability] = skill_id
            runtime_status_rows[skill_id] = _runtime_status_row(skill_id=skill_id, capability=capability, source=source)
            applied.append(
                {
                    "capability_id": capability,
                    "previous_skill_id": old_skill,
                    "skill_id": skill_id,
                    "decision": "runtime_primary_replaced",
                    "selection_rule": "min_token_delta_then_wall_delta_among_clean_live_approved",
                    "token_delta": (winner.get("delta") or {}).get("token_delta"),
                    "wall_delta": (winner.get("delta") or {}).get("wall_delta"),
                    "evidence_refs": [str(evidence.get("evidence_path") or "")],
                    "receipt_path": str(evidence.get("receipt_path") or ""),
                    "source_status": str(source.get("skill_status") or ""),
                    "requires_curation": requires_curation,
                    "runtime_review_scope": "overlay_only_requires_curation"
                    if requires_curation
                    else "overlay_only_curated",
                    "security_contract_version": SECURITY_CONTRACT_VERSION,
                    "promotion_credit_source": PROMOTION_CREDIT_SOURCE,
                    "v1_evidence_count": 1,
                    "v2_evidence_count": 0,
                    "v2_trust_mismatch_count": 0,
                    "requires_sandbox_attestation": True,
                    "sandbox_attestation_status": "missing_not_required_for_overlay_only",
                    "v2_promotion_eligible": False,
                }
            )
        else:
            source = status_by_skill.get(old_skill)
            if not source:
                blockers.append(f"{capability}:{old_skill}:missing_current_skill_status")
                continue
            runtime_status_rows[old_skill] = _runtime_status_row(skill_id=old_skill, capability=capability, source=source)
            kept.append({"capability_id": capability, "skill_id": old_skill, "decision": "runtime_primary_kept"})

    expected_count = len(current_overlay.get("primary_skill_by_capability") or {})
    if len(primary) != expected_count:
        blockers.append(f"capability_count_mismatch:{len(primary)}!={expected_count}")
    if not applied:
        blockers.append("no_clean_live_approved_replacements")

    external_reference_applied_count = sum(
        1 for row in applied if str(row.get("source_status") or "") == "external_reference_candidate"
    )
    requires_curation_count = sum(1 for row in applied if row.get("requires_curation") is True)
    v1_evidence_count = len(applied)
    v2_evidence_count = 0
    v2_trust_mismatch_count = 0
    status = "PASS" if not blockers else "RETURN"
    overlay = {
        "schema": "nexus.sf_final_runtime_skill_policy_overlay.applied.v1",
        "status": status,
        "created_at": datetime.now(UTC).isoformat(),
        "source_live_report": str(DEFAULT_LIVE_REPORT),
        "runtime_update_allowed": status == "PASS",
        "public_benchmark_allowed": False,
        "runtime_review_scope": "overlay_only",
        "security_contract_version": SECURITY_CONTRACT_VERSION,
        "promotion_credit_source": PROMOTION_CREDIT_SOURCE,
        "v1_evidence_count": v1_evidence_count,
        "v2_evidence_count": v2_evidence_count,
        "v2_trust_mismatch_count": v2_trust_mismatch_count,
        "requires_sandbox_attestation": True,
        "sandbox_attestation_status": "missing_not_required_for_overlay_only",
        "v2_promotion_eligible": False,
        "external_reference_applied_count": external_reference_applied_count,
        "requires_curation_count": requires_curation_count,
        "primary_skill_by_capability": dict(sorted(primary.items())) if status == "PASS" else {},
        "candidate_primary_skill_by_capability": dict(sorted(primary.items())) if status == "PASS" else {},
        "capability_aliases": current_overlay.get("capability_aliases", {}),
        "applied_primary": applied,
        "kept_primary": kept,
        "blockers": sorted(set(blockers)),
        "reject_conflict_warnings": sorted(
            reject_conflict_warnings,
            key=lambda item: (
                str(item.get("capability_id") or ""),
                str(item.get("skill_id") or ""),
                str(item.get("reject_capability") or ""),
            ),
        ),
        "claim_boundary": [
            "This overlay formally applies SF final live-approved runtime primary replacements.",
            "Runtime routes must still emit selected/injected/used/evidence/gate/outcome receipts.",
            "Public benchmark remains a separate gate.",
        ],
    }
    decision = {
        "schema": "nexus.sf_final_runtime_apply_decision.v1",
        "status": status,
        "created_at": overlay["created_at"],
        "summary": {
            "capability_count": len(primary) if status == "PASS" else 0,
            "applied_replacement_count": len(applied),
            "kept_primary_count": len(kept),
            "blocker_count": len(sorted(set(blockers))),
            "reject_conflict_warning_count": len(overlay["reject_conflict_warnings"]),
            "external_reference_applied_count": external_reference_applied_count,
            "requires_curation_count": requires_curation_count,
            "runtime_update_allowed": status == "PASS",
            "public_benchmark_allowed": False,
            "runtime_review_scope": "overlay_only",
            "security_contract_version": SECURITY_CONTRACT_VERSION,
            "promotion_credit_source": PROMOTION_CREDIT_SOURCE,
            "v1_evidence_count": v1_evidence_count,
            "v2_evidence_count": v2_evidence_count,
            "v2_trust_mismatch_count": v2_trust_mismatch_count,
            "requires_sandbox_attestation": True,
            "sandbox_attestation_status": "missing_not_required_for_overlay_only",
            "v2_promotion_eligible": False,
        },
        "applied_primary": applied,
        "kept_primary": kept,
        "blockers": overlay["blockers"],
        "reject_conflict_warnings": overlay["reject_conflict_warnings"],
        "claim_boundary": overlay["claim_boundary"],
    }
    merged_status = {
        "schema": "nexus.sf_final_runtime_skill_status_merged.v1",
        "summary": {
            "skill_count": len(runtime_status_rows),
            "applied_replacement_count": len(applied),
            "kept_primary_count": len(kept),
            "external_reference_applied_count": external_reference_applied_count,
            "requires_curation_count": requires_curation_count,
            "runtime_update_allowed": status == "PASS",
            "public_benchmark_allowed": False,
            "runtime_review_scope": "overlay_only",
            "security_contract_version": SECURITY_CONTRACT_VERSION,
            "promotion_credit_source": PROMOTION_CREDIT_SOURCE,
            "v1_evidence_count": v1_evidence_count,
            "v2_evidence_count": v2_evidence_count,
            "v2_trust_mismatch_count": v2_trust_mismatch_count,
            "requires_sandbox_attestation": True,
            "sandbox_attestation_status": "missing_not_required_for_overlay_only",
            "v2_promotion_eligible": False,
        },
        "skills": [runtime_status_rows[key] for key in sorted(runtime_status_rows)],
    }
    return {"decision": decision, "overlay": overlay, "skill_status": merged_status}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply SF final live-approved skill replacements to runtime overlay.")
    parser.add_argument("--current-overlay", default=str(DEFAULT_CURRENT_OVERLAY))
    parser.add_argument("--live-report", default=str(DEFAULT_LIVE_REPORT))
    parser.add_argument("--status-report", action="append", default=[str(DEFAULT_FINAL_STATUS), str(DEFAULT_CURRENT_STATUS)])
    parser.add_argument("--catalog-verdict-report", default=str(DEFAULT_CATALOG_VERDICTS))
    parser.add_argument("--decision-output", default=str(DEFAULT_DECISION))
    parser.add_argument("--overlay-output", default=str(DEFAULT_OVERLAY))
    parser.add_argument("--skill-status-output", default=str(DEFAULT_STATUS))
    args = parser.parse_args(argv)

    result = build_sf_final_runtime_apply(
        current_overlay=read_json(args.current_overlay),
        live_report=read_json(args.live_report),
        status_reports=[read_json(path) for path in args.status_report],
        catalog_verdict_report=read_json(args.catalog_verdict_report),
    )
    write_json(args.decision_output, result["decision"])
    write_json(args.overlay_output, result["overlay"])
    write_json(args.skill_status_output, result["skill_status"])
    print(
        json.dumps(
            {
                "status": result["decision"]["status"],
                "decision_output": args.decision_output,
                "overlay_output": args.overlay_output,
                "skill_status_output": args.skill_status_output,
                **result["decision"]["summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["decision"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
