#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json
from nexus.learning.zero_trust_v2_promotion import (
    READY_FOR_MANUAL_APPLY,
    evaluate_zero_trust_v2_promotion_candidate,
)


DEFAULT_REPLAY_MATRIX = Path("docs/reports/NEXUS_ZERO_TRUST_V2_REPLAY_MATRIX_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_PROMOTION_CANDIDATES_2026-05-21.json")


def _candidate_rows(replay_matrix: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        row
        for row in replay_matrix.get("rows", []) or []
        if isinstance(row, Mapping) and row.get("arm_type") in {"candidate_skill_v2", "shadow_candidate_v2"}
    ]


def build_zero_trust_v2_promotion_report(
    *, replay_matrix: Mapping[str, Any], min_v2_evidence_count: int = 3
) -> dict[str, Any]:
    candidates = []
    for row in _candidate_rows(replay_matrix):
        verdict = evaluate_zero_trust_v2_promotion_candidate(row, min_v2_evidence_count=min_v2_evidence_count)
        candidates.append(
            {
                "capability_id": verdict["capability_id"],
                "skill_id": verdict["skill_id"],
                "arm_type": row.get("arm_type", ""),
                "status": verdict["status"],
                "reasons": verdict["reasons"],
                "manual_apply_required": verdict["manual_apply_required"],
                "promotion_credit_source": verdict["promotion_credit_source"],
                "v2_evidence_count": verdict["v2_evidence_count"],
                "v2_trust_mismatch_count": verdict["v2_trust_mismatch_count"],
                "risk_flags": list(row.get("risk_flags") or []),
            }
        )
    status_counts = Counter(str(item["status"]) for item in candidates)
    ready = [item for item in candidates if item["status"] == READY_FOR_MANUAL_APPLY]
    return {
        "schema": "nexus.zero_trust_v2.promotion_report.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_replay_matrix": str(DEFAULT_REPLAY_MATRIX),
        "summary": {
            "candidate_arm_count": len(candidates),
            "ready_for_manual_apply_count": len(ready),
            "blocked_count": len(candidates) - len(ready),
            "status_counts": dict(sorted(status_counts.items())),
            "min_v2_evidence_count": min_v2_evidence_count,
            "promotion_credit_source": "v2_only",
            "runtime_mutation_allowed": False,
            "manual_apply_required": bool(ready),
            "public_benchmark_allowed": False,
        },
        "candidates": candidates,
        "claim_boundary": [
            "V1 evidence is diagnostic context only and never counts toward V2 promotion.",
            "READY_FOR_MANUAL_APPLY still requires a separate manual apply gate before runtime mutation.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 promotion candidate report.")
    parser.add_argument("--replay-matrix", default=str(DEFAULT_REPLAY_MATRIX))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--min-v2-evidence-count", type=int, default=3)
    args = parser.parse_args(argv)
    result = build_zero_trust_v2_promotion_report(
        replay_matrix=read_json(args.replay_matrix),
        min_v2_evidence_count=args.min_v2_evidence_count,
    )
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
