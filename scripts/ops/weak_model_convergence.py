from __future__ import annotations

import argparse
import glob
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_MAX_TOKEN_RATIO = 2.0
DEFAULT_MAX_WALL_RATIO = 2.5


@dataclass(frozen=True)
class GateThresholds:
    max_token_ratio: float = DEFAULT_MAX_TOKEN_RATIO
    max_wall_ratio: float = DEFAULT_MAX_WALL_RATIO


def _read_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected object JSON: {path}")
    return data


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _row_by_name(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for row in rows:
        if row.get("name") == name:
            return row
    raise ValueError(f"Missing row: {name}")


def _summarize_failed_runs(paths: list[str]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for path in sorted(paths):
        payload = _read_json(path)
        status = str(payload.get("status", "")).upper()
        if status == "PASSED":
            continue
        failures.append(
            {
                "run_id": payload.get("run_id") or Path(path).parent.name,
                "status": status or "UNKNOWN",
                "failed_task_id": payload.get("failed_task_id", ""),
                "root_cause": payload.get("root_cause", ""),
                "blocked_reason": payload.get("blocked_reason", ""),
                "with_nexus": payload.get("with_nexus", {}),
                "summary_path": path,
            }
        )
    return failures


def _cost_status(row: dict[str, Any], thresholds: GateThresholds) -> str:
    token_ratio = _safe_float(row.get("vs_reference_tokens_ratio"))
    wall_ratio = _safe_float(row.get("wall_ratio_vs_reference") or 0.0)
    if token_ratio > thresholds.max_token_ratio:
        return "too_expensive"
    if wall_ratio and wall_ratio > thresholds.max_wall_ratio:
        return "too_slow"
    return "acceptable"


def build_report(
    cost_truth: dict[str, Any],
    gap_matrix: dict[str, Any] | None,
    failed_summary_paths: list[str],
    thresholds: GateThresholds | None = None,
    *,
    require_holdout: bool = True,
    holdout_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or GateThresholds()
    rows = list(cost_truth.get("rows", []))
    reference_name = str(cost_truth.get("reference_model", "gpt55_bare"))
    student_name = str(cost_truth.get("weak_model_name", "flash_skip_baseline"))
    reference = _row_by_name(rows, reference_name)
    student = _row_by_name(rows, student_name)

    reference_verified_rate = _safe_float(reference.get("verified_rate"))
    student_verified_rate = _safe_float(student.get("verified_rate"))
    token_ratio = _safe_float(student.get("vs_reference_tokens_ratio"))
    wall_ratio = _safe_float(cost_truth.get("weak_model_decision", {}).get("weak_vs_reference_wall_ratio"))

    same_or_better_quality = student_verified_rate >= reference_verified_rate
    token_ok = token_ratio <= thresholds.max_token_ratio
    wall_ok = wall_ratio <= thresholds.max_wall_ratio
    default_policy_ok = student_name not in {"flash_skip_baseline"}
    failed_runs = _summarize_failed_runs(failed_summary_paths)
    no_regression_failures = not failed_runs
    holdout_validated = bool((gap_matrix or {}).get("holdout_validated", False))

    blockers: list[str] = []
    if not same_or_better_quality:
        blockers.append("weak_model_quality_below_gpt55_bare")
    if not token_ok:
        blockers.append("token_cost_above_launch_gate")
    if not wall_ok:
        blockers.append("wall_time_above_launch_gate")
    if not default_policy_ok:
        blockers.append("best_path_requires_non_default_skip_llm_baseline")
    if not no_regression_failures:
        blockers.append("recent_route_tuning_has_fail_fast_regressions")
    if require_holdout and not holdout_validated:
        blockers.append("holdout_validation_missing")

    treatment_rows: list[dict[str, Any]] = []
    for row in rows:
        row_name = str(row.get("name", ""))
        treatment_rows.append(
            {
                "name": row_name,
                "verified": row.get("verified"),
                "eligible": row.get("eligible"),
                "verified_rate": row.get("verified_rate"),
                "tokens_per_verified": row.get("tokens_per_verified"),
                "vs_reference_tokens_ratio": row.get("vs_reference_tokens_ratio"),
                "wall_per_verified_sec": row.get("wall_per_verified_sec"),
                "avg_model_calls": row.get("avg_model_calls"),
                "status": _cost_status(row, thresholds) if row_name != reference_name else "reference",
                "decision": row.get("decision"),
            }
        )

    gap_rows = list((gap_matrix or {}).get("rows", []))
    heavy_task_signals = [
        {
            "task_id": item.get("task_id"),
            "recommendation": item.get("recommendation"),
            "student_bare_verified": item.get("student_bare_verified"),
            "student_selected_count": item.get("student_selected_count"),
            "student_vs_teacher_token_ratio": item.get("student_vs_teacher_token_ratio"),
            "student_vs_teacher_wall_ratio": item.get("student_vs_teacher_wall_ratio"),
            "student_high_cost_selected": item.get("student_high_cost_selected", []),
        }
        for item in gap_rows
    ]
    feature_policy_candidate = build_feature_policy_candidate(heavy_task_signals)

    return {
        "schema_version": "nexus_weak_model_convergence_v1",
        "final_goal": "Gemini 3 Flash / Gemini 3.1 Pro with Nexus should approach GPT-5.5 bare quality on fixed public tasks with launchable cost.",
        "reference": reference_name,
        "student_candidate": student_name,
        "thresholds": {
            "max_token_ratio": thresholds.max_token_ratio,
            "max_wall_ratio": thresholds.max_wall_ratio,
        },
        "gate": {
            "same_or_better_quality": same_or_better_quality,
            "token_ok": token_ok,
            "wall_ok": wall_ok,
            "default_policy_ok": default_policy_ok,
            "no_regression_failures": no_regression_failures,
            "launchable": not blockers,
            "blockers": blockers,
        },
        "student_vs_reference": {
            "verified_rate_delta": round(student_verified_rate - reference_verified_rate, 4),
            "token_ratio": token_ratio,
            "wall_ratio": wall_ratio,
        },
        "treatment_rows": treatment_rows,
        "heavy_task_signals": heavy_task_signals,
        "feature_policy_candidate": feature_policy_candidate,
        "holdout_plan": holdout_plan or {},
        "failed_route_tuning_runs": failed_runs,
        "p11_p19_status": {
            "p11_freeze_goal": "done",
            "p12_cost_truth_matrix": "done",
            "p13_fail_fast_root_cause_capture": "done" if failed_runs else "done_no_recent_failures",
            "p14_launch_gate": "done",
            "p15_publishability_decision": "blocked" if blockers else "pass",
            "p16_route_tuning_input": "done",
            "p17_learning_loop_input": "done",
            "p18_next_experiment_queue": "done",
            "p20_feature_policy": "done",
            "p21_holdout_gate": "blocked" if require_holdout and not holdout_validated else "pass",
            "p22_anti_overfit_gate": "done",
            "p23_lite_standard_strict_candidate": "done",
            "p24_public_benchmark_readiness": "blocked" if blockers else "pass",
            "p25_runtime_policy_promotion": "blocked" if blockers else "ready",
            "p26_regression_tests": "done",
            "p27_nexus_self_test": "pending",
            "p28_flash_fail_fast": "pending",
            "p29_flash_4task_ab": "pending",
            "p30_pro_4task_ab": "pending",
            "p31_cost_loop": "blocked" if blockers else "pass",
            "p32_quality_loop": "blocked" if blockers else "pass",
            "p33_learning_writeback": "pending",
            "p34_convergence_gate": "done",
            "p35_public_holdout": "blocked" if require_holdout and not holdout_validated else "pass",
            "p36_public_report": "blocked" if blockers else "ready",
            "p37_dirty_cleanup": "pending",
            "p38_commit": "pending",
            "p39_single_blocker": blockers[0] if blockers else "",
            "p40_closure_decision": "partial_not_launchable" if blockers else "launchable_candidate",
        },
        "next_actions": [
            "Do not promote task-id route-cost policies; task_id is evidence only.",
            "Validate the feature policy candidate on a holdout task set before writing .nexus/policy/promoted_route_cost_policy.json.",
            "Promote no-skip default only after it matches skip-baseline cost without fail-fast regressions.",
            "Use feature selectors: if bare already verifies, cap selected capabilities and skip heavy research/hyper calls.",
            "Record route-cost lessons into the learning policy artifact before another Flash batch.",
            "Run same fixed tasks: GPT-5.5 bare reference, Flash bare, Flash+Nexus candidate, Pro+Nexus candidate.",
        ],
    }


def build_feature_policy_candidate(heavy_task_signals: list[dict[str, Any]]) -> dict[str, Any]:
    """Draft generalized route-cost rules without using task IDs as match keys."""
    task_ids = [str(item.get("task_id") or "") for item in heavy_task_signals if str(item.get("task_id") or "")]
    bare_verified_count = sum(1 for item in heavy_task_signals if bool(item.get("student_bare_verified", False)))
    nexus_required_count = sum(
        1 for item in heavy_task_signals if str(item.get("recommendation") or "") == "nexus_required_but_student_runtime_too_heavy"
    )
    high_cost_caps = sorted(
        {
            str(cap)
            for item in heavy_task_signals
            for cap in (item.get("student_high_cost_selected", []) or [])
            if str(cap)
        }
    )
    rules: list[dict[str, Any]] = []
    if bare_verified_count:
        rules.append(
            {
                "name": "bare_verified_lite_route",
                "match": {
                    "bare_verified": True,
                    "risk_not_high": True,
                    "explicit_research_demand": False,
                },
                "action": {
                    "route_tier": "lite",
                    "candidate_cap": 1,
                    "disable_self_heal": True,
                    "preserve_gates": ["claim_gate", "delivery_gate", "artifact_gate"],
                },
                "evidence_count": bare_verified_count,
            }
        )
    if nexus_required_count:
        rules.append(
            {
                "name": "nexus_required_standard_route",
                "match": {
                    "bare_verified": False,
                    "nexus_required": True,
                },
                "action": {
                    "route_tier": "standard",
                    "candidate_cap": 1,
                    "preserve_gates": ["claim_gate", "delivery_gate", "artifact_gate", "belief"],
                },
                "evidence_count": nexus_required_count,
            }
        )
    if high_cost_caps:
        rules.append(
            {
                "name": "high_cost_research_cap",
                "match": {
                    "high_cost_selected_any": high_cost_caps,
                    "substantive_evidence_demand": False,
                },
                "action": {
                    "downgrade_high_cost_conditionals": True,
                    "candidate_cap": 1,
                },
                "evidence_count": len(high_cost_caps),
            }
        )
    return {
        "schema": "nexus_route_cost_feature_policy_candidate_v1",
        "status": "DRAFT_NOT_PROMOTED",
        "runtime_match_uses_task_id": False,
        "task_ids_are_evidence_only": task_ids,
        "holdout_required_before_promotion": True,
        "rules": rules,
    }


def render_markdown(report: dict[str, Any]) -> str:
    gate = report["gate"]
    lines = [
        "# P11-P19 Weak Model Convergence Report",
        "",
        f"Final goal: {report['final_goal']}",
        f"Decision: {'PASS' if gate['launchable'] else 'BLOCKED'}",
        "",
        "## Gate",
    ]
    for key, value in gate.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Student vs GPT-5.5 Bare"])
    for key, value in report["student_vs_reference"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Treatments"])
    for row in report["treatment_rows"]:
        lines.append(
            "- {name}: verified={verified}/{eligible}, token_ratio={ratio}, calls={calls}, status={status}".format(
                name=row["name"],
                verified=row.get("verified"),
                eligible=row.get("eligible"),
                ratio=row.get("vs_reference_tokens_ratio"),
                calls=row.get("avg_model_calls"),
                status=row.get("status"),
            )
        )
    lines.extend(["", "## Failed Route Tuning Runs"])
    if report["failed_route_tuning_runs"]:
        for failure in report["failed_route_tuning_runs"]:
            lines.append(
                f"- {failure['run_id']}: failed_task={failure['failed_task_id']}, reason={failure['root_cause']}"
            )
    else:
        lines.append("- none")
    lines.extend(["", "## P11-P19 Status"])
    for key, value in report["p11_p19_status"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Next Actions"])
    for action in report["next_actions"]:
        lines.append(f"- {action}")
    lines.extend(["", "## Feature Policy Candidate", "", "```json"])
    lines.append(json.dumps(report["feature_policy_candidate"], ensure_ascii=False, indent=2))
    lines.extend(["```"])
    if report.get("holdout_plan"):
        lines.extend(["", "## Holdout Plan", "", "```json"])
        lines.append(json.dumps(report["holdout_plan"], ensure_ascii=False, indent=2))
        lines.extend(["```"])
    lines.append("")
    return "\n".join(lines)


def build_holdout_plan(
    *,
    task_manifest: dict[str, Any],
    excluded_task_ids: set[str],
    max_tasks: int = 4,
) -> dict[str, Any]:
    tasks = task_manifest.get("tasks", task_manifest if isinstance(task_manifest, list) else [])
    if not isinstance(tasks, list):
        tasks = []
    selected: list[dict[str, Any]] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id") or "")
        if not task_id or task_id in excluded_task_ids:
            continue
        selected.append(task)
        if len(selected) >= max_tasks:
            break
    return {
        "schema": "nexus_weak_model_holdout_plan_v1",
        "selection_policy": "exclude_tuning_task_ids_take_manifest_order",
        "runtime_match_uses_task_id": False,
        "excluded_task_ids": sorted(excluded_task_ids),
        "task_count": len(selected),
        "task_ids": [str(task.get("id") or "") for task in selected],
        "tasks": selected,
        "required_before_promotion": True,
        "commands": {
            "flash_fail_fast": "run capability_ab_runner on this holdout manifest with Gemini 3 Flash, stop on first failure",
            "pro_fail_fast": "run capability_ab_runner on this holdout manifest with Gemini 3.1 Pro, stop on first failure",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build weak-model convergence report from measured Nexus benchmark artifacts.")
    parser.add_argument("--cost-truth", required=True)
    parser.add_argument("--gap-matrix")
    parser.add_argument("--failed-summary-glob", action="append", default=[])
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--max-token-ratio", type=float, default=DEFAULT_MAX_TOKEN_RATIO)
    parser.add_argument("--max-wall-ratio", type=float, default=DEFAULT_MAX_WALL_RATIO)
    parser.add_argument("--allow-missing-holdout", action="store_true")
    parser.add_argument("--feature-policy-output")
    parser.add_argument("--holdout-task-manifest")
    parser.add_argument("--holdout-output")
    parser.add_argument("--holdout-max-tasks", type=int, default=4)
    args = parser.parse_args()

    failed_paths: list[str] = []
    for pattern in args.failed_summary_glob:
        failed_paths.extend(glob.glob(pattern))

    gap_matrix = _read_json(args.gap_matrix) if args.gap_matrix else None
    excluded_task_ids = {
        str(row.get("task_id") or "")
        for row in ((gap_matrix or {}).get("rows", []) or [])
        if isinstance(row, dict) and str(row.get("task_id") or "")
    }
    holdout_plan = None
    if args.holdout_task_manifest:
        holdout_plan = build_holdout_plan(
            task_manifest=_read_json(args.holdout_task_manifest),
            excluded_task_ids=excluded_task_ids,
            max_tasks=max(1, int(args.holdout_max_tasks)),
        )

    report = build_report(
        cost_truth=_read_json(args.cost_truth),
        gap_matrix=gap_matrix,
        failed_summary_paths=failed_paths,
        thresholds=GateThresholds(args.max_token_ratio, args.max_wall_ratio),
        require_holdout=not args.allow_missing_holdout,
        holdout_plan=holdout_plan,
    )

    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    output_md.write_text(render_markdown(report), encoding="utf-8")
    if args.feature_policy_output:
        feature_policy_output = Path(args.feature_policy_output)
        feature_policy_output.parent.mkdir(parents=True, exist_ok=True)
        feature_policy_output.write_text(
            json.dumps(report["feature_policy_candidate"], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if args.holdout_output and holdout_plan is not None:
        holdout_output = Path(args.holdout_output)
        holdout_output.parent.mkdir(parents=True, exist_ok=True)
        holdout_output.write_text(
            json.dumps(
                {
                    "schema": "nexus_public_benchmark_holdout_manifest_v1",
                    "source_manifest": str(args.holdout_task_manifest),
                    "tasks": holdout_plan["tasks"],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    print(json.dumps({"launchable": report["gate"]["launchable"], "blockers": report["gate"]["blockers"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
