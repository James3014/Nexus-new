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

from nexus.learning.zero_trust_v2_promotion import READY_FOR_MANUAL_APPLY
from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_PROMOTION_REPORT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_PROMOTION_CANDIDATES_2026-05-21.json")
DEFAULT_M45_M52 = Path("docs/reports/NEXUS_ZERO_TRUST_V2_M45_M52_COMPLETION_2026-05-22.json")
DEFAULT_MANUAL_TRIAL = Path("docs/reports/NEXUS_ZERO_TRUST_V2_MANUAL_APPLY_TRIAL_2026-05-21.json")
DEFAULT_ROLLOUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_P0_ROLLOUT_2026-05-21.json")
DEFAULT_CURRENT_OVERLAY = Path("docs/reports/NEXUS_SF_FINAL_RUNTIME_SKILL_POLICY_OVERLAY_APPLIED_2026-05-21.json")
DEFAULT_CURRENT_SKILL_STATUS = Path("docs/reports/NEXUS_SF_FINAL_RUNTIME_SKILL_STATUS_MERGED_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_RUNTIME_APPLY_PLAN_2026-05-21.json")
DEFAULT_APPLIED_OVERLAY = Path("docs/reports/NEXUS_ZERO_TRUST_V2_RUNTIME_SKILL_POLICY_OVERLAY_APPLIED_2026-05-22.json")
DEFAULT_APPLIED_STATUS = Path("docs/reports/NEXUS_ZERO_TRUST_V2_RUNTIME_SKILL_STATUS_MERGED_2026-05-22.json")


def _ready_candidates(promotion_report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        item
        for item in promotion_report.get("candidates", []) or []
        if isinstance(item, Mapping) and item.get("status") == READY_FOR_MANUAL_APPLY
    ]


def build_zero_trust_v2_runtime_apply_plan(*, promotion_report: Mapping[str, Any]) -> dict[str, Any]:
    ready = _ready_candidates(promotion_report)
    patch_plan = [
        {
            "capability_id": str(item.get("capability_id") or ""),
            "skill_id": str(item.get("skill_id") or ""),
            "action": "manual_runtime_overlay_update",
            "requires_operator_ack": True,
            "requires_revert_plan": True,
            "allowed_only_after_review": True,
        }
        for item in ready
    ]
    return {
        "schema": "nexus.zero_trust_v2.runtime_apply_plan.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_promotion_report": str(DEFAULT_PROMOTION_REPORT),
        "summary": {
            "ready_for_manual_apply_count": len(ready),
            "patch_plan_count": len(patch_plan),
            "runtime_update_allowed": False,
            "automatic_apply_allowed": False,
            "manual_operator_ack_required": bool(patch_plan),
            "revert_plan_required": bool(patch_plan),
            "public_benchmark_allowed": False,
        },
        "patch_plan": patch_plan,
        "blockers": [
            "no_ready_v2_candidates" if not patch_plan else "manual_operator_ack_missing",
        ],
        "claim_boundary": [
            "This artifact is an apply plan only; it must not mutate runtime skill maps.",
            "V2 runtime mutation requires explicit manual operator acknowledgement and a revert plan.",
        ],
    }


def _summary(report: Mapping[str, Any]) -> Mapping[str, Any]:
    summary = report.get("summary")
    return summary if isinstance(summary, Mapping) else {}


def _clean_receipt_refs(m45_m52: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    refs: dict[tuple[str, str], dict[str, Any]] = {}
    for item in m45_m52.get("m45_behavior_run_results", []) or []:
        if not isinstance(item, Mapping):
            continue
        capability_id = str(item.get("capability_id") or "")
        skill_id = str(item.get("skill_id") or "")
        if not capability_id or not skill_id:
            continue
        key = (capability_id, skill_id)
        row = refs.setdefault(
            key,
            {
                "clean_v2_receipt_count": 0,
                "runtime_signed_receipt_verified_count": 0,
                "evidence_refs": [],
                "blockers": set(),
            },
        )
        if item.get("clean_v2_receipt") is True:
            row["clean_v2_receipt_count"] += 1
        if item.get("runtime_signed_receipt_verified") is True:
            row["runtime_signed_receipt_verified_count"] += 1
        evidence_bundle = str(item.get("evidence_bundle") or "")
        if evidence_bundle:
            row["evidence_refs"].append(evidence_bundle)
        for blocker in item.get("blockers", []) or []:
            if blocker:
                row["blockers"].add(str(blocker))
    return refs


def _manual_apply_ready(manual_trial: Mapping[str, Any]) -> bool:
    return bool(manual_trial.get("status") == "PASS" and _summary(manual_trial).get("manual_apply_trial_ready") is True)


def _rollout_ready(rollout_report: Mapping[str, Any]) -> bool:
    summary = _summary(rollout_report)
    return bool(
        rollout_report.get("status") == "PASS"
        and summary.get("p0_rollout_complete") is True
        and summary.get("p1_p2_rollout_complete") is True
        and int(summary.get("promoted_count") or 0) == int(summary.get("candidate_count") or -1)
        and int(summary.get("candidate_count") or 0) >= 34
    )


def _current_status_by_name(skill_status_report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows: dict[str, Mapping[str, Any]] = {}
    for item in skill_status_report.get("skills", []) or []:
        if isinstance(item, Mapping) and str(item.get("name") or ""):
            rows[str(item.get("name") or "")] = item
    return rows


def build_zero_trust_v2_runtime_apply_artifacts(
    *,
    promotion_report: Mapping[str, Any],
    m45_m52: Mapping[str, Any],
    manual_trial: Mapping[str, Any],
    rollout_report: Mapping[str, Any],
    current_overlay: Mapping[str, Any],
    current_skill_status: Mapping[str, Any],
) -> dict[str, Any]:
    ready = _ready_candidates(promotion_report)
    ready_by_capability = {str(item.get("capability_id") or ""): item for item in ready}
    current_primary = current_overlay.get("primary_skill_by_capability")
    current_primary = current_primary if isinstance(current_primary, Mapping) else {}
    receipt_refs = _clean_receipt_refs(m45_m52)
    blockers: list[str] = []
    if current_overlay.get("status") != "PASS":
        blockers.append("current_runtime_overlay_not_pass")
    if int(_summary(m45_m52).get("m45_clean_v2_receipt_count") or 0) < 102:
        blockers.append("clean_v2_receipt_count_lt_102")
    if int(_summary(m45_m52).get("m51_v2_ready_capability_count") or 0) < 34:
        blockers.append("v2_ready_capability_count_lt_34")
    if len(ready_by_capability) != 34:
        blockers.append(f"ready_for_manual_apply_count_not_34:{len(ready_by_capability)}")
    if set(ready_by_capability) != set(str(key) for key in current_primary):
        blockers.append("ready_capability_set_does_not_match_current_runtime_overlay")
    if not _manual_apply_ready(manual_trial):
        blockers.append("manual_apply_trial_not_ready")
    if not _rollout_ready(rollout_report):
        blockers.append("p0_p1_p2_rollout_not_complete")

    applied: list[dict[str, Any]] = []
    primary: dict[str, str] = {}
    for capability_id, item in sorted(ready_by_capability.items()):
        skill_id = str(item.get("skill_id") or "")
        key = (capability_id, skill_id)
        receipt = receipt_refs.get(key, {})
        receipt_blockers = sorted(str(blocker) for blocker in receipt.get("blockers", set()))
        if int(receipt.get("clean_v2_receipt_count") or 0) < 3:
            blockers.append(f"{capability_id}:{skill_id}:clean_v2_receipt_count_lt_3")
        if receipt_blockers:
            blockers.append(f"{capability_id}:{skill_id}:receipt_blockers_present")
        primary[capability_id] = skill_id
        applied.append(
            {
                "capability_id": capability_id,
                "previous_skill_id": str(current_primary.get(capability_id) or ""),
                "skill_id": skill_id,
                "priority": str(item.get("priority") or ""),
                "decision": "v2_default_primary_applied",
                "selection_rule": "runtime_signed_v2_receipt_3_of_3_then_manual_batch_rollout",
                "v2_behavior_evidence_count": int(item.get("v2_behavior_evidence_count") or 0),
                "clean_v2_receipt_count": int(receipt.get("clean_v2_receipt_count") or 0),
                "runtime_signed_receipt_verified_count": int(receipt.get("runtime_signed_receipt_verified_count") or 0),
                "evidence_refs": list(receipt.get("evidence_refs") or []),
                "failed_security_contract_rules": sorted(set(item.get("failed_security_contract_rules") or [])),
                "promotion_credit_source": "v2_only",
                "security_contract_version": "zero_trust_v2_runtime_signed",
            }
        )

    status = "PASS" if not blockers else "BLOCKED"
    created_at = datetime.now(UTC).isoformat()
    overlay = {
        "schema": "nexus.zero_trust_v2.runtime_skill_policy_overlay.applied.v1",
        "status": status,
        "created_at": created_at,
        "source_promotion_report": str(DEFAULT_PROMOTION_REPORT),
        "source_m45_m52": str(DEFAULT_M45_M52),
        "source_manual_trial": str(DEFAULT_MANUAL_TRIAL),
        "source_rollout": str(DEFAULT_ROLLOUT),
        "runtime_update_allowed": status == "PASS",
        "runtime_mutation_allowed": status == "PASS",
        "automatic_apply_allowed": False,
        "public_benchmark_allowed": False,
        "security_contract_version": "zero_trust_v2_runtime_signed",
        "promotion_credit_source": "v2_only",
        "v1_fallback_mode": "rollback_only",
        "v2_evidence_count": sum(item["clean_v2_receipt_count"] for item in applied),
        "v2_ready_capability_count": len(primary) if status == "PASS" else 0,
        "v2_trust_mismatch_count": 0,
        "primary_skill_by_capability": dict(sorted(primary.items())) if status == "PASS" else {},
        "candidate_primary_skill_by_capability": dict(sorted(primary.items())) if status == "PASS" else {},
        "capability_aliases": current_overlay.get("capability_aliases", {}),
        "applied_primary": applied if status == "PASS" else [],
        "blockers": sorted(set(blockers)),
        "claim_boundary": [
            "This overlay applies Zero-Trust V2 runtime-signed behavior evidence to the internal runtime default lane.",
            "Public benchmark remains a separate gate and is not unlocked by this apply.",
            "V1 remains rollback-only until a separate closure decision removes the fallback path.",
        ],
    }
    decision = {
        "schema": "nexus.zero_trust_v2.runtime_apply_decision.v1",
        "status": status,
        "created_at": created_at,
        "summary": {
            "capability_count": len(primary) if status == "PASS" else 0,
            "ready_for_manual_apply_count": len(ready),
            "v2_default_applied_count": len(applied) if status == "PASS" else 0,
            "clean_v2_receipt_count": sum(item["clean_v2_receipt_count"] for item in applied),
            "manual_apply_trial_ready": _manual_apply_ready(manual_trial),
            "p0_rollout_complete": bool(_summary(rollout_report).get("p0_rollout_complete")),
            "p1_p2_rollout_complete": bool(_summary(rollout_report).get("p1_p2_rollout_complete")),
            "runtime_update_allowed": status == "PASS",
            "runtime_mutation_allowed": status == "PASS",
            "automatic_apply_allowed": False,
            "public_benchmark_allowed": False,
            "post_apply_smoke_required": status == "PASS",
            "security_contract_version": "zero_trust_v2_runtime_signed",
            "promotion_credit_source": "v2_only",
        },
        "applied_primary": applied if status == "PASS" else [],
        "blockers": sorted(set(blockers)),
        "claim_boundary": overlay["claim_boundary"],
    }
    current_status = _current_status_by_name(current_skill_status)
    status_rows = []
    for item in applied:
        source = dict(current_status.get(item["skill_id"], {}))
        source.update(
            {
                "name": item["skill_id"],
                "action": "runtime_policy_overlay_only",
                "capability_mount": item["capability_id"],
                "family": item["capability_id"],
                "runtime_review_scope": "zero_trust_v2_default_overlay",
                "security_contract_version": "zero_trust_v2_runtime_signed",
                "promotion_credit_source": "v2_only",
                "v2_evidence_count": item["clean_v2_receipt_count"],
                "v2_trust_mismatch_count": 0,
                "v2_promotion_eligible": True,
                "requires_sandbox_attestation": False,
                "sandbox_attestation_status": "covered_by_runtime_signed_behavior_receipts",
            }
        )
        status_rows.append(source)
    merged_status = {
        "schema": "nexus.zero_trust_v2.runtime_skill_status_merged.v1",
        "status": status,
        "created_at": created_at,
        "summary": {
            "skill_count": len(status_rows),
            "v2_default_applied_count": len(applied) if status == "PASS" else 0,
            "runtime_update_allowed": status == "PASS",
            "runtime_mutation_allowed": status == "PASS",
            "public_benchmark_allowed": False,
            "security_contract_version": "zero_trust_v2_runtime_signed",
            "promotion_credit_source": "v2_only",
            "v2_evidence_count": sum(item["clean_v2_receipt_count"] for item in applied),
            "v2_trust_mismatch_count": 0,
        },
        "skills": status_rows if status == "PASS" else [],
    }
    return {"decision": decision, "overlay": overlay, "skill_status": merged_status}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 manual runtime apply plan.")
    parser.add_argument("--promotion-report", default=str(DEFAULT_PROMOTION_REPORT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--m45-m52", default="")
    parser.add_argument("--manual-trial", default="")
    parser.add_argument("--rollout-report", default="")
    parser.add_argument("--current-overlay", default=str(DEFAULT_CURRENT_OVERLAY))
    parser.add_argument("--current-skill-status", default=str(DEFAULT_CURRENT_SKILL_STATUS))
    parser.add_argument("--decision-output", default="")
    parser.add_argument("--overlay-output", default=str(DEFAULT_APPLIED_OVERLAY))
    parser.add_argument("--skill-status-output", default=str(DEFAULT_APPLIED_STATUS))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    promotion_report = read_json(args.promotion_report)
    if args.apply:
        result = build_zero_trust_v2_runtime_apply_artifacts(
            promotion_report=promotion_report,
            m45_m52=read_json(args.m45_m52 or DEFAULT_M45_M52),
            manual_trial=read_json(args.manual_trial or DEFAULT_MANUAL_TRIAL),
            rollout_report=read_json(args.rollout_report or DEFAULT_ROLLOUT),
            current_overlay=read_json(args.current_overlay),
            current_skill_status=read_json(args.current_skill_status),
        )
        decision_output = args.decision_output or args.output
        write_json(decision_output, result["decision"])
        write_json(args.overlay_output, result["overlay"])
        write_json(args.skill_status_output, result["skill_status"])
        print(
            json.dumps(
                {
                    "status": result["decision"]["status"],
                    "decision_output": decision_output,
                    "overlay_output": args.overlay_output,
                    "skill_status_output": args.skill_status_output,
                    **result["decision"]["summary"],
                },
                sort_keys=True,
            )
        )
        return 0 if result["decision"]["status"] == "PASS" else 1

    result = build_zero_trust_v2_runtime_apply_plan(promotion_report=promotion_report)
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
