from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PHASES: tuple[tuple[str, str], ...] = (
    ("phase0_boundary", "Separate bare model, model wearing Nexus, Nexus tool, and invalid success sources."),
    ("phase1_baseline", "Freeze 12-task weak-model versus GPT-5.5 teacher benchmark loop."),
    ("phase2_cost_attribution", "Attribute cost by model calls, phase, capability, and route friction."),
    ("phase3_route_policy", "Tune route tiers with cost, risk, learning, and evidence signals."),
    ("phase4_learning_loops", "Project verified episodes into Nexus policy and model-training exports."),
    ("phase5_long_sweep", "Run Flash/Pro wearing Nexus against teacher gap until promotion gates pass."),
    ("phase6_fail_loop", "Stop on the first failed task, diagnose trace, patch route, and rerun."),
    ("phase7_real_tasks", "Shadow-check non-benchmark tasks to prevent task-id overfitting."),
    ("phase8_registry", "Ensure full capability registry has cost, risk, evidence, and receipt contracts."),
    ("phase9_closure", "Publish only eligible weak-model uplift, cost avoidance, and residual-debt reports."),
)


@dataclass(frozen=True)
class ClassifiedRow:
    task_id: str
    classification: str
    recommendation: str
    reason: str
    model_uplift_eligible: bool


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _ratio(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_gap_row(row: dict[str, Any]) -> ClassifiedRow:
    task_id = str(row.get("task_id") or "")
    source = str(row.get("student_success_source") or "")
    recommendation = str(row.get("recommendation") or "")
    uplift = bool(row.get("student_model_uplift_eligible", False))
    student_verified = bool(row.get("student_verified", False))
    teacher_verified = bool(row.get("teacher_verified", False))
    wall_ratio = _ratio(row.get("student_vs_teacher_wall_ratio"))
    token_ratio = _ratio(row.get("student_vs_teacher_token_ratio"))

    if source in {"local_deterministic_success", "nexus_tool_success"}:
        return ClassifiedRow(
            task_id=task_id,
            classification="nexus_cost_avoidance_not_model_uplift",
            recommendation="keep_separate_from_weak_model_claims",
            reason=f"success_source={source}; model_uplift_eligible=false",
            model_uplift_eligible=False,
        )
    if not student_verified and teacher_verified:
        return ClassifiedRow(
            task_id=task_id,
            classification="weak_model_capability_gap",
            recommendation="diagnose_route_or_context_gap_before_more_runs",
            reason="teacher verified but student wearing Nexus failed",
            model_uplift_eligible=False,
        )
    if uplift and student_verified:
        if (wall_ratio is not None and wall_ratio > 2.0) or (token_ratio is not None and token_ratio > 2.0):
            return ClassifiedRow(
                task_id=task_id,
                classification="model_uplift_cost_too_high",
                recommendation="tune_cost_aware_route_then_rerun_same_task",
                reason=f"eligible uplift but cost ratio wall={wall_ratio} token={token_ratio}",
                model_uplift_eligible=True,
            )
        return ClassifiedRow(
            task_id=task_id,
            classification="model_uplift_candidate",
            recommendation="promote_if_same_model_ab_holds",
            reason=f"eligible uplift with recommendation={recommendation}",
            model_uplift_eligible=True,
        )
    if student_verified:
        return ClassifiedRow(
            task_id=task_id,
            classification="verified_but_not_public_uplift",
            recommendation="inspect_eligibility_before_claim",
            reason="verified row lacks model-uplift eligibility",
            model_uplift_eligible=False,
        )
    return ClassifiedRow(
        task_id=task_id,
        classification="unverified_gap",
        recommendation="stop_on_task_and_diagnose_trace",
        reason="student row is not verified",
        model_uplift_eligible=False,
    )


def build_closure_plan(*, gap_payload: dict[str, Any], min_task_count: int) -> dict[str, Any]:
    rows = [classify_gap_row(dict(row)) for row in list(gap_payload.get("rows", []) or [])]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.classification] = counts.get(row.classification, 0) + 1
    model_uplift_rows = [row for row in rows if row.model_uplift_eligible]
    local_rows = [row for row in rows if row.classification == "nexus_cost_avoidance_not_model_uplift"]
    needs_more_tasks = len(rows) < min_task_count
    has_actionable_uplift = bool(model_uplift_rows)
    phase_status: list[dict[str, str]] = []
    for name, goal in PHASES:
        if name == "phase0_boundary":
            status = "complete" if rows else "blocked"
        elif name == "phase1_baseline":
            status = "complete" if not needs_more_tasks else "needs_more_task_coverage"
        elif name in {"phase2_cost_attribution", "phase3_route_policy", "phase5_long_sweep"}:
            status = "ready" if has_actionable_uplift else "blocked_until_model_uplift_rows_exist"
        elif name == "phase9_closure":
            status = "ready" if len(rows) >= min_task_count and has_actionable_uplift else "not_ready"
        else:
            status = "ready"
        phase_status.append({"phase": name, "goal": goal, "status": status})
    return {
        "schema_version": "nexus_weak_model_closure_plan_v1",
        "student_model": str(gap_payload.get("student_model") or ""),
        "teacher_model": str(gap_payload.get("teacher_model") or ""),
        "min_task_count": min_task_count,
        "task_count": len(rows),
        "classification_counts": counts,
        "model_uplift_eligible_task_count": len(model_uplift_rows),
        "nexus_cost_avoidance_task_count": len(local_rows),
        "closure_ready": len(rows) >= min_task_count and has_actionable_uplift,
        "phase_status": phase_status,
        "rows": [
            {
                "task_id": row.task_id,
                "classification": row.classification,
                "recommendation": row.recommendation,
                "reason": row.reason,
                "model_uplift_eligible": row.model_uplift_eligible,
            }
            for row in rows
        ],
        "next_required_action": _next_required_action(rows=rows, min_task_count=min_task_count),
    }


def _next_required_action(*, rows: list[ClassifiedRow], min_task_count: int) -> str:
    if len(rows) < min_task_count:
        return "expand_to_12_task_teacher_student_loop_before_claims"
    if not any(row.model_uplift_eligible for row in rows):
        return "run_model_calling_flash_or_pro_nexus_tasks; local_tool_success_is_not_enough"
    if any(row.classification == "model_uplift_cost_too_high" for row in rows):
        return "tune_cost_aware_route_for_high_cost_eligible_uplift_rows"
    if any(row.classification in {"weak_model_capability_gap", "unverified_gap"} for row in rows):
        return "stop_on_failed_task_and_diagnose_trace_before_more_runs"
    return "run_same_model_ab_and_publish_only_if_public_gate_passes"


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Nexus Weak Model Closure Plan",
        "",
        f"- student: `{payload['student_model']}`",
        f"- teacher: `{payload['teacher_model']}`",
        f"- task_count: `{payload['task_count']}` / `{payload['min_task_count']}`",
        f"- closure_ready: `{payload['closure_ready']}`",
        f"- next_required_action: `{payload['next_required_action']}`",
        "",
        "## Classification Counts",
        "",
    ]
    for name, count in sorted(payload["classification_counts"].items()):
        lines.append(f"- `{name}`: {count}")
    lines.extend(["", "## Phase Status", ""])
    for phase in payload["phase_status"]:
        lines.append(f"- `{phase['phase']}`: {phase['status']} - {phase['goal']}")
    lines.extend(["", "## Task Decisions", "", "| Task | Classification | Eligible | Recommendation | Reason |", "| :--- | :--- | :--- | :--- | :--- |"])
    for row in payload["rows"]:
        lines.append(
            f"| {row['task_id']} | {row['classification']} | {row['model_uplift_eligible']} | "
            f"{row['recommendation']} | {row['reason']} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a Phase 0-9 weak-model Nexus closure plan from teacher/student gap data.")
    parser.add_argument("--gap-json", required=True)
    parser.add_argument("--min-task-count", type=int, default=12)
    parser.add_argument("--output", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)

    payload = build_closure_plan(gap_payload=_load_json(Path(args.gap_json)), min_task_count=int(args.min_task_count))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(payload), encoding="utf-8")
    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
