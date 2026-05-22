#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_PROMOTION = Path("docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_PROMOTION_REPORT_2026-05-21.json")
DEFAULT_MANUAL_TRIAL = Path("docs/reports/NEXUS_ZERO_TRUST_V2_MANUAL_APPLY_TRIAL_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_P0_ROLLOUT_2026-05-21.json")


def _manual_ready(manual_trial: dict | None) -> bool:
    if manual_trial is None:
        return False
    summary = manual_trial.get("summary") if isinstance(manual_trial.get("summary"), dict) else {}
    return bool(manual_trial.get("status") == "PASS" and summary.get("manual_apply_trial_ready") is True)


def build_zero_trust_v2_p0_rollout(*, promotion_report: dict, manual_trial: dict | None = None) -> dict:
    manual_apply_ready = _manual_ready(manual_trial)
    candidates = [item for item in promotion_report.get("candidates", []) or [] if isinstance(item, dict)]
    items = []
    for item in candidates:
        ready = item.get("status") == "READY_FOR_MANUAL_APPLY" and manual_apply_ready
        status = "V2_PROMOTED_TO_DEFAULT_OVERLAY" if ready else (
            "V2_READY_MANUAL_APPLY_PENDING" if item.get("status") == "READY_FOR_MANUAL_APPLY" else "STRUCTURED_BLOCKED"
        )
        items.append(
            {
                "capability_id": item.get("capability_id", ""),
                "skill_id": item.get("skill_id", ""),
                "priority": item.get("priority", ""),
                "rollout_status": status,
                "p0_rollout_status": status if item.get("priority") == "P0" else "NOT_P0",
                "fallback_incident_required_if_v1_used": status in {"V2_READY_MANUAL_APPLY_PENDING", "STRUCTURED_BLOCKED"},
                "failed_security_contract_rules": list(item.get("failed_security_contract_rules") or []),
            }
        )
    p0_items = [item for item in items if item.get("priority") == "P0"]
    p1_p2_items = [item for item in items if item.get("priority") in {"P1", "P2"}]
    p0_counts = Counter(item["rollout_status"] for item in p0_items)
    p1_p2_counts = Counter(item["rollout_status"] for item in p1_p2_items)
    all_counts = Counter(item["rollout_status"] for item in items)
    return {
        "schema": "nexus.zero_trust_v2.batch_rollout.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_promotion_report": str(DEFAULT_PROMOTION),
        "source_manual_trial": str(DEFAULT_MANUAL_TRIAL),
        "summary": {
            "candidate_count": len(items),
            "promoted_count": all_counts.get("V2_PROMOTED_TO_DEFAULT_OVERLAY", 0),
            "manual_apply_trial_ready": manual_apply_ready,
            "p0_candidate_count": len(p0_items),
            "p0_ready_count": p0_counts.get("V2_READY_MANUAL_APPLY_PENDING", 0),
            "p0_promoted_count": p0_counts.get("V2_PROMOTED_TO_DEFAULT_OVERLAY", 0),
            "p0_structured_blocked_count": p0_counts.get("STRUCTURED_BLOCKED", 0),
            "p0_rollout_complete": bool(p0_items) and p0_counts.get("V2_PROMOTED_TO_DEFAULT_OVERLAY", 0) == len(p0_items),
            "p1_p2_candidate_count": len(p1_p2_items),
            "p1_p2_ready_count": p1_p2_counts.get("V2_READY_MANUAL_APPLY_PENDING", 0),
            "p1_p2_promoted_count": p1_p2_counts.get("V2_PROMOTED_TO_DEFAULT_OVERLAY", 0),
            "p1_p2_structured_blocked_count": p1_p2_counts.get("STRUCTURED_BLOCKED", 0),
            "p1_p2_rollout_complete": bool(p1_p2_items)
            and p1_p2_counts.get("V2_PROMOTED_TO_DEFAULT_OVERLAY", 0) == len(p1_p2_items),
            "runtime_mutation_allowed": manual_apply_ready,
            "public_benchmark_allowed": False,
        },
        "items": items,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 P0 rollout packet.")
    parser.add_argument("--promotion-report", default=str(DEFAULT_PROMOTION))
    parser.add_argument("--manual-trial", default="")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_zero_trust_v2_p0_rollout(
        promotion_report=read_json(args.promotion_report),
        manual_trial=read_json(args.manual_trial) if args.manual_trial else None,
    )
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
