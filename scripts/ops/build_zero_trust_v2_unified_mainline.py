#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_M45_M52 = Path("docs/reports/NEXUS_ZERO_TRUST_V2_M45_M52_COMPLETION_2026-05-22.json")
DEFAULT_MANUAL_TRIAL = Path("docs/reports/NEXUS_ZERO_TRUST_V2_MANUAL_APPLY_TRIAL_2026-05-21.json")
DEFAULT_ROLLOUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_P0_ROLLOUT_2026-05-21.json")
DEFAULT_RUNTIME_APPLY = Path("docs/reports/NEXUS_ZERO_TRUST_V2_RUNTIME_APPLY_PLAN_2026-05-21.json")
DEFAULT_POST_APPLY_SMOKE = Path("docs/reports/NEXUS_ZERO_TRUST_V2_RUNTIME_POST_APPLY_SMOKE_2026-05-22.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_UNIFIED_MAINLINE_2026-05-22.json")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _blocker_set(m45_m52: dict[str, Any]) -> set[str]:
    blockers: set[str] = set()
    for item in _as_list(m45_m52.get("m45_behavior_run_results")):
        if isinstance(item, dict):
            blockers.update(str(blocker) for blocker in _as_list(item.get("blockers")) if str(blocker))
    for item in _as_list(_as_dict(m45_m52.get("m46_receipt_import_gate")).get("dominant_blockers")):
        if isinstance(item, dict) and item.get("reason"):
            blockers.add(str(item["reason"]))
    return blockers


def _milestone(id_: str, title: str, *, blockers: list[str], acceptance: str, next_action: str) -> dict[str, Any]:
    return {
        "milestone": id_,
        "title": title,
        "status": "PASS" if not blockers else "BLOCKED",
        "blockers": blockers,
        "acceptance": acceptance,
        "next_action": next_action,
    }


def _manual_trial_blockers(manual_trial: dict[str, Any] | None) -> list[str]:
    if not manual_trial:
        return ["manual_apply_trial_report_missing"]
    summary = _as_dict(manual_trial.get("summary"))
    if manual_trial.get("status") != "PASS" or summary.get("manual_apply_trial_ready") is not True:
        return list(manual_trial.get("blockers") or ["manual_apply_trial_not_ready"])
    return []


def _rollout_blockers(rollout: dict[str, Any] | None, *, p1_p2: bool = False) -> list[str]:
    if not rollout:
        return ["rollout_report_missing"]
    summary = _as_dict(rollout.get("summary"))
    key = "p1_p2_rollout_complete" if p1_p2 else "p0_rollout_complete"
    if rollout.get("status") != "PASS" or summary.get(key) is not True:
        return [f"{key}_not_complete"]
    return []


def _runtime_apply_blockers(runtime_apply: dict[str, Any] | None) -> list[str]:
    if not runtime_apply:
        return ["runtime_apply_decision_missing"]
    summary = _as_dict(runtime_apply.get("summary"))
    if runtime_apply.get("status") != "PASS" or summary.get("runtime_update_allowed") is not True:
        return list(runtime_apply.get("blockers") or ["runtime_apply_not_pass"])
    if int(summary.get("v2_default_applied_count") or 0) < 34:
        return ["v2_default_applied_count_lt_34"]
    return []


def _post_smoke_blockers(post_apply_smoke: dict[str, Any] | None) -> list[str]:
    if not post_apply_smoke:
        return ["post_apply_smoke_missing"]
    summary = _as_dict(post_apply_smoke.get("summary"))
    if post_apply_smoke.get("status") != "PASS":
        return ["post_apply_smoke_not_pass"]
    if int(summary.get("case_count") or 0) != 34 or int(summary.get("pass_count") or 0) != 34:
        return ["post_apply_smoke_not_34_of_34"]
    return []


def build_zero_trust_v2_unified_mainline(
    *,
    m45_m52: dict[str, Any],
    manual_trial: dict[str, Any] | None = None,
    rollout: dict[str, Any] | None = None,
    runtime_apply: dict[str, Any] | None = None,
    post_apply_smoke: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blockers = _blocker_set(m45_m52)
    clean_receipts = int(_as_dict(m45_m52.get("summary")).get("m45_clean_v2_receipt_count") or 0)
    v2_ready_capabilities = int(_as_dict(m45_m52.get("summary")).get("m51_v2_ready_capability_count") or 0)
    m53_blockers = [b for b in ("missing_required_capability_receipts", "receipt_data_contract_violation") if b in blockers]
    m54_blockers = ["missing_runtime_signed_v2_receipt"] if "missing_runtime_signed_v2_receipt" in blockers else []
    m55_blockers = [b for b in ("no_eligible_behavior_row", "semantic_not_verified") if b in blockers]
    m56_blockers = ["clean_v2_receipt_count_lt_3"] if clean_receipts < 3 else []
    canary_blockers = sorted(set(m53_blockers + m54_blockers + m55_blockers + m56_blockers))
    manual_blockers = _manual_trial_blockers(manual_trial) if not canary_blockers else ["canary_not_clean"]
    canary_apply_blockers = manual_blockers
    p0_blockers = _rollout_blockers(rollout) if not canary_apply_blockers else ["manual_apply_trial_not_ready"]
    p1_p2_blockers = _rollout_blockers(rollout, p1_p2=True) if not p0_blockers else ["p0_rollout_not_complete"]
    coverage_blocker = ["v2_ready_capability_count_lt_34"] if v2_ready_capabilities < 34 else []
    runtime_apply_blockers = _runtime_apply_blockers(runtime_apply) if not coverage_blocker and not p1_p2_blockers else ["rollout_or_coverage_not_complete"]
    smoke_blockers = _post_smoke_blockers(post_apply_smoke) if not runtime_apply_blockers else ["v2_default_overlay_not_applied"]

    milestones = [
        _milestone(
            "M53",
            "expected_capability_receipt_bridge",
            blockers=m53_blockers,
            acceptance="expected capability coverage has no missing public-safe receipts",
            next_action="repair mempalace_gate public-safe receipt source before more canary runs",
        ),
        _milestone(
            "M54",
            "runtime_signed_behavior_receipt_export",
            blockers=m54_blockers,
            acceptance="verify_runtime_signed_receipt passes for every imported behavior bundle",
            next_action="export runtime observer signature into evidence bundle",
        ),
        _milestone(
            "M55",
            "canary_semantic_delivery_repair",
            blockers=m55_blockers,
            acceptance="eligible_behavior_rows>=1 and semantic_completed=true",
            next_action="repair model delivery path or task execution route",
        ),
        _milestone(
            "M56",
            "canary_three_clean_receipts",
            blockers=m56_blockers,
            acceptance="3/3 clean V2 behavior receipts for the canary candidate",
            next_action="rerun run-01/run-02/run-03 only after M53-M55 pass",
        ),
        _milestone(
            "M57",
            "manual_apply_trial_packet",
            blockers=manual_blockers,
            acceptance="manual apply trial packet exists with explicit operator acknowledgement",
            next_action="generate trial packet after receipt import passes",
        ),
        _milestone(
            "M58",
            "canary_dry_run_apply_and_rollback",
            blockers=canary_apply_blockers,
            acceptance="dry-run overlay diff, smoke command, and rollback command are present",
            next_action="prepare canary apply only after manual ack",
        ),
        _milestone(
            "M59",
            "p0_batch_rollout",
            blockers=p0_blockers,
            acceptance="all P0 candidates have clean receipts and rollback proof",
            next_action="run P0 after canary apply/rollback passes",
        ),
        _milestone(
            "M60",
            "p1_p2_batch_rollout",
            blockers=p1_p2_blockers,
            acceptance="all P1/P2 candidates have clean receipts and rollback proof",
            next_action="run P1/P2 only after P0 is clean",
        ),
        _milestone(
            "M61",
            "thirty_four_capability_coverage",
            blockers=coverage_blocker,
            acceptance="v2_ready_capability_count=34",
            next_action="generate fresh tasks for missing capability coverage",
        ),
        _milestone(
            "M62",
            "v1_closure_decision",
            blockers=coverage_blocker,
            acceptance="closure apply plan is allowed only after 34/34 V2-ready capabilities",
            next_action="keep V1 fallback path active",
        ),
        _milestone(
            "M63",
            "v2_default_overlay_apply",
            blockers=runtime_apply_blockers,
            acceptance="operator-approved V2 default overlay is applied with rollback path",
            next_action="do not mutate runtime until closure decision passes",
        ),
        _milestone(
            "M64",
            "post_unification_smoke_and_public_gate",
            blockers=smoke_blockers,
            acceptance="34/34 smoke passes; public benchmark gate remains separately reviewed",
            next_action="separate internal V2 unification from public claim unlock",
        ),
    ]
    status_counts: dict[str, int] = {}
    for item in milestones:
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
    unified = all(item["status"] == "PASS" for item in milestones)
    return {
        "schema": "nexus.zero_trust_v2.unified_mainline.v1",
        "status": "PASS" if unified else "BLOCKED",
        "created_at": datetime.now(UTC).isoformat(),
        "source_m45_m52": str(DEFAULT_M45_M52),
        "summary": {
            "milestone_count": len(milestones),
            "milestone_pass_count": status_counts.get("PASS", 0),
            "milestone_blocked_count": status_counts.get("BLOCKED", 0),
            "clean_v2_receipt_count": clean_receipts,
            "v2_ready_capability_count": v2_ready_capabilities,
            "v2_unification_complete": unified,
            "runtime_mutation_allowed": bool(unified),
            "automatic_apply_allowed": False,
            "public_benchmark_allowed": False,
            "promotion_credit_allowed": bool(unified),
        },
        "milestones": milestones,
        "root_blockers": sorted(blockers),
        "claim_boundary": [
            "V2 runtime unification is internal-only and does not unlock public benchmark claims.",
            "Runtime mutation is allowed only when M53-M64 all pass with clean evidence.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 unified mainline closeout.")
    parser.add_argument("--m45-m52", default=str(DEFAULT_M45_M52))
    parser.add_argument("--manual-trial", default="")
    parser.add_argument("--rollout", default="")
    parser.add_argument("--runtime-apply", default="")
    parser.add_argument("--post-apply-smoke", default="")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_zero_trust_v2_unified_mainline(
        m45_m52=read_json(args.m45_m52),
        manual_trial=read_json(args.manual_trial) if args.manual_trial else None,
        rollout=read_json(args.rollout) if args.rollout else None,
        runtime_apply=read_json(args.runtime_apply) if args.runtime_apply else None,
        post_apply_smoke=read_json(args.post_apply_smoke) if args.post_apply_smoke else None,
    )
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
