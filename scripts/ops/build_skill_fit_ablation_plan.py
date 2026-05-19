#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_ablation import write_skill_fit_ablation_plan, write_skill_fit_execution_matrix


DEFAULT_POOL = Path("docs/reports/NEXUS_FAIR_SKILL_CANDIDATE_POOL_2026-05-15.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_SKILL_FIT_ABLATION_PLAN_REPAIR_AND_CODING_EXPANDED_2026-05-16.json")
DEFAULT_LANE_MANIFEST = Path("scripts/bench/public_benchmark_commercial_lanes_v1.json")
DEFAULT_MATRIX_OUTPUT = Path("docs/reports/NEXUS_SKILL_FIT_EXECUTION_MATRIX_REPAIR_AND_CODING_FLASH180_2026-05-16.json")
DEFAULT_EXTRA_TASK_MANIFESTS = (
    "scripts/bench/public_benchmark_pilot_v1.json",
    "scripts/bench/public_benchmark_hard_neutral_v2.json",
    "scripts/bench/public_benchmark_rlm_harder_v1.json",
    "scripts/bench/public_benchmark_docs_lane_v1.json",
)


def resolved_extra_task_manifests(explicit_manifests: list[str] | None) -> list[str]:
    """Use built-in extras only when the caller did not provide an explicit set."""

    if explicit_manifests is None:
        return list(DEFAULT_EXTRA_TASK_MANIFESTS)
    return explicit_manifests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a receipt-gated fair skill-fit ablation plan.")
    parser.add_argument("--candidate-pool", default=str(DEFAULT_POOL))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--capability", default="repair_and_coding")
    parser.add_argument("--max-skill-arms", type=int, default=4)
    parser.add_argument("--explicit-skill-id", action="append", default=[])
    parser.add_argument("--no-wrong-arm", action="store_true")
    parser.add_argument("--matrix-output", default=str(DEFAULT_MATRIX_OUTPUT))
    parser.add_argument("--lane-manifest", default=str(DEFAULT_LANE_MANIFEST))
    parser.add_argument("--lane-id", default="cost_efficiency,expanded_commercial_50")
    parser.add_argument("--extra-task-manifest", action="append", default=None)
    parser.add_argument("--matrix-max-tasks", type=int, default=30)
    parser.add_argument("--model", default="gemini-3-flash-preview")
    parser.add_argument("--runner", default="scripts/bench/capability_ab_runner.py")
    parser.add_argument("--skill-status-report", default="docs/reports/NEXUS_SKILL_STATUS_2026-05-15.json")
    parser.add_argument("--skip-matrix", action="store_true")
    args = parser.parse_args(argv)

    plan = write_skill_fit_ablation_plan(
        candidate_pool_path=args.candidate_pool,
        output_path=args.output,
        capability=args.capability,
        max_skill_arms=args.max_skill_arms,
        include_wrong_arm=not args.no_wrong_arm,
        explicit_skill_ids=args.explicit_skill_id,
    )
    summary = {
        "status": plan["status"],
        "output": args.output,
        "capability": plan["capability"],
        **plan["summary"],
    }
    if not args.skip_matrix and plan["status"] == "PASS":
        matrix = write_skill_fit_execution_matrix(
            plan_path=args.output,
            lane_manifest_path=args.lane_manifest,
            lane_id=args.lane_id,
            output_path=args.matrix_output,
            extra_task_manifests=resolved_extra_task_manifests(args.extra_task_manifest),
            max_tasks=args.matrix_max_tasks,
            model=args.model,
            runner=args.runner,
            skill_status_report=args.skill_status_report,
        )
        summary.update(
            {
                "matrix_status": matrix["status"],
                "matrix_output": args.matrix_output,
                "matrix_row_count": matrix["summary"]["row_count"],
                "matrix_task_count": matrix["summary"]["task_count"],
            }
        )
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if plan["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
