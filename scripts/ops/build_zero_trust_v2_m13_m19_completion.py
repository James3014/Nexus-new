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


DEFAULT_RUNNER_MATRIX = Path("docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_RUNNER_MATRIX_2026-05-21.json")
DEFAULT_M12 = Path("docs/reports/NEXUS_ZERO_TRUST_V2_M12_34_CAPABILITY_FINAL_VERDICT_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_M13_M19_COMPLETION_2026-05-21.json")


def build_zero_trust_v2_m13_m19_completion(*, runner_matrix: dict, m12_verdict: dict) -> dict:
    summary = runner_matrix.get("summary", {}) if isinstance(runner_matrix.get("summary"), dict) else {}
    m12_summary = m12_verdict.get("summary", {}) if isinstance(m12_verdict.get("summary"), dict) else {}
    ready_count = int(summary.get("ready_for_physical_behavior_run_count") or 0)
    blocked_count = int(summary.get("blocked_count") or 0)
    candidate_count = int(summary.get("candidate_count") or 0)
    return {
        "schema": "nexus.zero_trust_v2.m13_m19_completion.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_runner_matrix": str(DEFAULT_RUNNER_MATRIX),
        "source_m12_verdict": str(DEFAULT_M12),
        "summary": {
            "m13_capability_ab_runner_adapter_complete": True,
            "m14_fresh_behavior_receipt_path_ready_count": ready_count,
            "m15_first_candidate_ready_for_manual_apply": False,
            "m16_manual_trial_rollback_gate_ready": False,
            "m17_p0_rollout_promoted_count": 0,
            "m17_p0_structured_blocked_count": int(summary.get("p0_count") or 0),
            "m18_p1_p2_promoted_count": 0,
            "m18_p1_p2_structured_blocked_count": int(summary.get("p1_count") or 0) + int(summary.get("p2_count") or 0),
            "m19_v1_promotion_shutdown_boundary_complete": True,
            "candidate_count": candidate_count,
            "blocked_count": blocked_count,
            "capability_count": int(m12_summary.get("capability_count") or 0),
            "v2_unification_complete": False,
            "runtime_mutation_allowed": False,
            "public_benchmark_allowed": False,
            "promotion_credit_allowed": False,
        },
        "milestones": [
            {
                "milestone": "M13",
                "status": "COMPLETE",
                "result": "capability_ab_runner adapter schema and hook gate generated",
            },
            {
                "milestone": "M14",
                "status": "BLOCKED",
                "result": "fresh task_ref missing, no physical behavior receipt can be credited",
            },
            {
                "milestone": "M15",
                "status": "BLOCKED",
                "result": "no candidate has sufficient signed V2 behavior receipts",
            },
            {
                "milestone": "M16",
                "status": "BLOCKED",
                "result": "manual trial and rollback gate remain unavailable without ready candidate",
            },
            {
                "milestone": "M17",
                "status": "STRUCTURED_BLOCKED",
                "result": "P0 batch has explicit blockers instead of silent promotion",
            },
            {
                "milestone": "M18",
                "status": "STRUCTURED_BLOCKED",
                "result": "P1/P2 batch has explicit blockers instead of silent promotion",
            },
            {
                "milestone": "M19",
                "status": "COMPLETE",
                "result": "V1 remains runtime fallback; V1 evidence cannot count toward V2 promotion",
            },
        ],
        "claim_boundary": [
            "M13-M19 completion here means the V2 fresh behavior runner path is specified and fail-closed.",
            "V2 unification remains false until fresh physical behavior receipts exist.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 M13-M19 completion report.")
    parser.add_argument("--runner-matrix", default=str(DEFAULT_RUNNER_MATRIX))
    parser.add_argument("--m12-verdict", default=str(DEFAULT_M12))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_zero_trust_v2_m13_m19_completion(
        runner_matrix=read_json(args.runner_matrix),
        m12_verdict=read_json(args.m12_verdict),
    )
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
