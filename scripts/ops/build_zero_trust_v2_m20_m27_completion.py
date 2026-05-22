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


DEFAULT_FRESH_TASK_REFS = Path("docs/reports/NEXUS_ZERO_TRUST_V2_FRESH_TASK_REFS_2026-05-21.json")
DEFAULT_RUNNER_MATRIX = Path("docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_RUNNER_MATRIX_2026-05-21.json")
DEFAULT_M12 = Path("docs/reports/NEXUS_ZERO_TRUST_V2_M12_34_CAPABILITY_FINAL_VERDICT_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_M20_M27_COMPLETION_2026-05-21.json")


def build_zero_trust_v2_m20_m27_completion(*, fresh_task_refs: dict, runner_matrix: dict, m12_verdict: dict) -> dict:
    fresh_summary = fresh_task_refs.get("summary", {}) if isinstance(fresh_task_refs.get("summary"), dict) else {}
    matrix_summary = runner_matrix.get("summary", {}) if isinstance(runner_matrix.get("summary"), dict) else {}
    m12_summary = m12_verdict.get("summary", {}) if isinstance(m12_verdict.get("summary"), dict) else {}
    ready_to_run = int(matrix_summary.get("ready_for_physical_behavior_run_count") or 0)
    p0_count = int(matrix_summary.get("p0_count") or 0)
    p1_p2_count = int(matrix_summary.get("p1_count") or 0) + int(matrix_summary.get("p2_count") or 0)
    capability_count = int(m12_summary.get("capability_count") or 0)
    return {
        "schema": "nexus.zero_trust_v2.m20_m27_completion.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_fresh_task_refs": str(DEFAULT_FRESH_TASK_REFS),
        "source_runner_matrix": str(DEFAULT_RUNNER_MATRIX),
        "source_m12_verdict": str(DEFAULT_M12),
        "summary": {
            "m20_fresh_task_ref_count": int(fresh_summary.get("fresh_task_ref_count") or 0),
            "m21_ready_for_physical_behavior_run_count": ready_to_run,
            "m21_physical_behavior_executed_count": 0,
            "m22_clean_v2_receipt_count": 0,
            "m23_manual_apply_trial_ready_count": 0,
            "m24_low_risk_canary_ready": False,
            "m25_p0_promoted_count": 0,
            "m25_p0_structured_blocked_count": p0_count,
            "m26_p1_p2_promoted_count": 0,
            "m26_p1_p2_structured_blocked_count": p1_p2_count,
            "m27_capability_count": capability_count,
            "m27_v2_ready_capability_count": 0,
            "m27_v1_promotion_path_closed": False,
            "v2_unification_complete": False,
            "runtime_mutation_allowed": False,
            "automatic_apply_allowed": False,
            "public_benchmark_allowed": False,
            "promotion_credit_allowed": False,
        },
        "milestones": [
            {"milestone": "M20", "status": "COMPLETE", "result": "fresh task_ref manifest generated for all current V2 candidates"},
            {"milestone": "M21", "status": "READY_TO_RUN", "result": "physical behavior commands are prepared; model/sandbox execution not run in this artifact"},
            {"milestone": "M22", "status": "BLOCKED", "result": "no signed clean V2 behavior receipts accumulated yet"},
            {"milestone": "M23", "status": "BLOCKED", "result": "manual apply trial remains blocked without ready candidate"},
            {"milestone": "M24", "status": "BLOCKED", "result": "low-risk canary replacement requires at least one manual-apply-ready candidate"},
            {"milestone": "M25", "status": "STRUCTURED_BLOCKED", "result": "P0 batch has execution path but no promotion receipts"},
            {"milestone": "M26", "status": "STRUCTURED_BLOCKED", "result": "P1/P2 batch has execution path but no promotion receipts"},
            {"milestone": "M27", "status": "BOUNDARY_COMPLETE", "result": "V1 shutdown boundary is enforced, but V1 path is not closed until all 34 capabilities are V2 ready"},
        ],
        "rollback_gate": {
            "required_before_runtime_mutation": True,
            "rollback_target": "restore_v1_runtime_overlay_primary",
            "requires_previous_skill_id": True,
            "smoke_required": True,
            "operator_ack_required": True,
            "post_apply_smoke_required": True,
        },
        "claim_boundary": [
            "M20-M27 completion here means every downstream decision has an explicit artifact and fail-closed status.",
            "No runtime default is changed and no V2 unification claim is allowed without fresh signed behavior receipts.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 M20-M27 completion report.")
    parser.add_argument("--fresh-task-refs", default=str(DEFAULT_FRESH_TASK_REFS))
    parser.add_argument("--runner-matrix", default=str(DEFAULT_RUNNER_MATRIX))
    parser.add_argument("--m12-verdict", default=str(DEFAULT_M12))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_zero_trust_v2_m20_m27_completion(
        fresh_task_refs=read_json(args.fresh_task_refs),
        runner_matrix=read_json(args.runner_matrix),
        m12_verdict=read_json(args.m12_verdict),
    )
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
