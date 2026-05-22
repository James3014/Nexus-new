#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_PROMOTION = Path("docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_PROMOTION_REPORT_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_MANUAL_APPLY_TRIAL_2026-05-21.json")


def build_zero_trust_v2_manual_trial(*, promotion_report: dict, operator_ack: str = "") -> dict:
    ready = [item for item in promotion_report.get("candidates", []) or [] if isinstance(item, dict) and item.get("status") == "READY_FOR_MANUAL_APPLY"]
    dry_run_patch_plan = [
        {
            "capability_id": item.get("capability_id", ""),
            "skill_id": item.get("skill_id", ""),
            "action": "dry_run_v2_primary_with_v1_fallback",
            "operator_ack_required": True,
            "operator_ack_status": "ACKNOWLEDGED" if operator_ack else "MISSING",
            "revert_plan": "restore_v1_runtime_overlay_primary",
            "rollback_proof": "v1_runtime_overlay_primary_can_be_restored_before_public_claims",
        }
        for item in ready
    ]
    acked = bool(operator_ack)
    blockers = []
    if not dry_run_patch_plan:
        blockers.append("no_v2_ready_candidate_for_manual_trial")
    if dry_run_patch_plan and not acked:
        blockers.append("manual_operator_ack_missing")
    return {
        "schema": "nexus.zero_trust_v2.manual_apply_trial.v1",
        "status": "PASS" if dry_run_patch_plan and acked else "BLOCKED",
        "created_at": datetime.now(UTC).isoformat(),
        "source_promotion_report": str(DEFAULT_PROMOTION),
        "summary": {
            "ready_candidate_count": len(ready),
            "trial_patch_plan_count": len(dry_run_patch_plan),
            "manual_apply_trial_ready": bool(dry_run_patch_plan) and acked,
            "operator_ack_status": "ACKNOWLEDGED" if acked else "MISSING",
            "operator_ack_source": operator_ack,
            "runtime_mutation_allowed": bool(dry_run_patch_plan) and acked,
            "automatic_apply_allowed": False,
            "smoke_required_before_apply": bool(dry_run_patch_plan),
            "public_benchmark_allowed": False,
        },
        "dry_run_patch_plan": dry_run_patch_plan,
        "blockers": blockers,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 manual apply trial packet.")
    parser.add_argument("--promotion-report", default=str(DEFAULT_PROMOTION))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--operator-ack", default="")
    args = parser.parse_args(argv)
    result = build_zero_trust_v2_manual_trial(
        promotion_report=read_json(args.promotion_report),
        operator_ack=args.operator_ack,
    )
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
