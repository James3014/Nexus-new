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


DEFAULT_BEHAVIOR = Path("docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_EVIDENCE_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_PROMOTION_REPORT_2026-05-21.json")


def build_zero_trust_v2_behavior_promotion_report(*, behavior_evidence: dict, min_v2_evidence_count: int = 3) -> dict:
    candidates = []
    for item in behavior_evidence.get("candidates", []) or []:
        if not isinstance(item, dict):
            continue
        reasons = list(item.get("failed_security_contract_rules") or [])
        if int(item.get("v2_behavior_evidence_count") or 0) < min_v2_evidence_count:
            reasons.append("INSUFFICIENT_V2_BEHAVIOR_EVIDENCE")
        status = "READY_FOR_MANUAL_APPLY" if not reasons else "BLOCKED"
        candidates.append(
            {
                "capability_id": item.get("capability_id", ""),
                "skill_id": item.get("skill_id", ""),
                "priority": item.get("priority", ""),
                "status": status,
                "v2_behavior_evidence_count": int(item.get("v2_behavior_evidence_count") or 0),
                "failed_security_contract_rules": sorted(set(reasons)),
            }
        )
    status_counts = Counter(candidate["status"] for candidate in candidates)
    return {
        "schema": "nexus.zero_trust_v2.behavior_promotion_report.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_behavior_evidence": str(DEFAULT_BEHAVIOR),
        "summary": {
            "candidate_count": len(candidates),
            "ready_for_manual_apply_count": status_counts.get("READY_FOR_MANUAL_APPLY", 0),
            "blocked_count": status_counts.get("BLOCKED", 0),
            "min_v2_evidence_count": min_v2_evidence_count,
            "runtime_mutation_allowed": False,
            "public_benchmark_allowed": False,
        },
        "candidates": candidates,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 behavior promotion report.")
    parser.add_argument("--behavior-evidence", default=str(DEFAULT_BEHAVIOR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--min-v2-evidence-count", type=int, default=3)
    args = parser.parse_args(argv)
    result = build_zero_trust_v2_behavior_promotion_report(
        behavior_evidence=read_json(args.behavior_evidence),
        min_v2_evidence_count=args.min_v2_evidence_count,
    )
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
