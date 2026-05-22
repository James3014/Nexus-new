#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_EVIDENCE = Path("docs/reports/NEXUS_ZERO_TRUST_V2_PHYSICAL_SKILL_EVIDENCE_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_EVIDENCE_ACCUMULATION_2026-05-21.json")


def build_zero_trust_v2_evidence_accumulation(*, physical_evidence: dict, min_v2_evidence_count: int = 3) -> dict:
    rows = [row for row in physical_evidence.get("rows", []) or [] if isinstance(row, dict)]
    by_candidate: dict[tuple[str, str], dict] = defaultdict(lambda: {"v2_evidence_count": 0, "v2_trust_mismatch_count": 0, "negative_control_blocked_count": 0, "rows": []})
    for row in rows:
        if row.get("arm_type") not in {"candidate_skill_v2", "shadow_candidate_v2", "wrong_or_quarantined_skill_v2"}:
            continue
        key = (str(row.get("capability_id") or ""), str(row.get("source_skill_id") or row.get("skill_id") or ""))
        item = by_candidate[key]
        item["rows"].append(row.get("row_id"))
        item["v2_evidence_count"] += int(row.get("v2_evidence_count") or 0)
        item["v2_trust_mismatch_count"] += int(row.get("v2_trust_mismatch_count") or 0)
        item["negative_control_blocked_count"] += int(row.get("negative_control_blocked_count") or 0)
    candidates = []
    for (capability_id, skill_id), item in sorted(by_candidate.items()):
        ready = (
            item["v2_evidence_count"] >= min_v2_evidence_count
            and item["v2_trust_mismatch_count"] == 0
            and item["negative_control_blocked_count"] >= 1
        )
        candidates.append(
            {
                "capability_id": capability_id,
                "skill_id": skill_id,
                "status": "READY_FOR_MANUAL_APPLY" if ready else "BLOCKED",
                "v2_evidence_count": item["v2_evidence_count"],
                "v2_trust_mismatch_count": item["v2_trust_mismatch_count"],
                "negative_control_blocked_count": item["negative_control_blocked_count"],
                "row_refs": item["rows"],
            }
        )
    status_counts = Counter(candidate["status"] for candidate in candidates)
    return {
        "schema": "nexus.zero_trust_v2.evidence_accumulation.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_physical_evidence": str(DEFAULT_EVIDENCE),
        "summary": {
            "candidate_count": len(candidates),
            "ready_for_manual_apply_count": status_counts.get("READY_FOR_MANUAL_APPLY", 0),
            "blocked_count": status_counts.get("BLOCKED", 0),
            "min_v2_evidence_count": min_v2_evidence_count,
            "materialization_only": bool(physical_evidence.get("summary", {}).get("materialization_only")),
            "runtime_mutation_allowed": False,
            "public_benchmark_allowed": False,
        },
        "candidates": candidates,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 evidence accumulation report.")
    parser.add_argument("--physical-evidence", default=str(DEFAULT_EVIDENCE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--min-v2-evidence-count", type=int, default=3)
    args = parser.parse_args(argv)
    result = build_zero_trust_v2_evidence_accumulation(
        physical_evidence=read_json(args.physical_evidence),
        min_v2_evidence_count=args.min_v2_evidence_count,
    )
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
