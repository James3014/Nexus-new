#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.bench.teacher_reference_gate import build_teacher_reference_gate
from scripts.ops.nexus_pre_flash_gate import build_payload as build_pre_flash_payload


def build_p110_launch_candidate_gate(
    *,
    repo_root: Path,
    teacher_run: Path,
    student_runs: dict[str, Path],
    teacher_arm: str = "without_nexus",
    min_quality_ratio: float = 0.9,
    min_overlap_tasks: int = 4,
    target_teacher_tasks: int = 8,
    max_wall_ratio: float = 1.8,
    max_median_wall_ratio: float = 1.5,
    max_token_ratio: float = 1.3,
    run_pre_flash: bool = True,
) -> dict[str, Any]:
    teacher_gate = build_teacher_reference_gate(
        teacher_run=teacher_run,
        teacher_arm=teacher_arm,
        student_runs=student_runs,
        min_quality_ratio=min_quality_ratio,
        min_overlap_tasks=min_overlap_tasks,
    )
    pre_flash = (
        build_pre_flash_payload(repo_root, run_repair=False, output_dir=".nexus/reports/p110_pre_flash_gate", write_artifacts=False)
        if run_pre_flash
        else {"passed": True, "checks": [], "failures": []}
    )
    cost = _evaluate_cost(teacher_gate, max_wall_ratio=max_wall_ratio, max_median_wall_ratio=max_median_wall_ratio, max_token_ratio=max_token_ratio)
    readiness_blockers = []
    pre_flash_warnings = _pre_flash_warnings(pre_flash)
    warnings = list(teacher_gate.get("warnings", [])) + cost["warnings"] + pre_flash_warnings

    if not teacher_gate.get("passed"):
        readiness_blockers.append({"reason": "teacher_reference_gate_failed", "failures": teacher_gate.get("failures", [])})
    if not pre_flash.get("passed"):
        readiness_blockers.append({"reason": "pre_flash_gate_failed", "failures": pre_flash.get("failures", [])})
    if int(teacher_gate.get("teacher_tasks", 0) or 0) < target_teacher_tasks:
        readiness_blockers.append(
            {
                "reason": "teacher_reference_suite_below_launch_target",
                "teacher_tasks": teacher_gate.get("teacher_tasks", 0),
                "target_teacher_tasks": target_teacher_tasks,
            }
        )
    if cost["hard_failures"]:
        readiness_blockers.append({"reason": "cost_gate_failed", "failures": cost["hard_failures"]})

    quality_ready = bool(teacher_gate.get("passed") and pre_flash.get("passed") and not cost["hard_failures"])
    launch_ready = quality_ready and not readiness_blockers
    return {
        "schema_version": "nexus_p110_launch_candidate_gate.v1",
        "quality_ready": quality_ready,
        "launch_ready": launch_ready,
        "passed": launch_ready,
        "target": {
            "statement": "Gemini 3 Flash / Gemini 3.1 Pro wearing Nexus approaches GPT-5.5 direct on fixed public tasks with trust-safe, cost-disciplined always-on routing.",
            "teacher_reference_tasks_required_for_launch": target_teacher_tasks,
            "min_quality_ratio_vs_gpt55_direct": min_quality_ratio,
            "max_wall_ratio": max_wall_ratio,
            "max_median_wall_ratio": max_median_wall_ratio,
            "max_token_ratio": max_token_ratio,
        },
        "teacher_reference_gate": teacher_gate,
        "pre_flash_gate": {
            "passed": pre_flash.get("passed"),
            "check_count": len(pre_flash.get("checks", [])),
            "failures": pre_flash.get("failures", []),
            "warnings": pre_flash_warnings,
        },
        "cost_gate": cost,
        "warnings": warnings,
        "readiness_blockers": readiness_blockers,
        "next_actions": _next_actions(readiness_blockers, warnings),
    }


def _evaluate_cost(
    teacher_gate: dict[str, Any],
    *,
    max_wall_ratio: float,
    max_median_wall_ratio: float,
    max_token_ratio: float,
) -> dict[str, Any]:
    hard_failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    students = teacher_gate.get("students", [])
    for student in students if isinstance(students, list) else []:
        if not isinstance(student, dict):
            continue
        name = str(student.get("student") or "")
        checks = student.get("public_claim_checks", {})
        checks = checks if isinstance(checks, dict) else {}
        wall = _float(checks.get("wall_cost_ratio"))
        median_wall = _float(checks.get("median_paired_wall_cost_ratio"))
        token = _float(checks.get("token_cost_ratio"))
        if wall > max_wall_ratio and median_wall > max_median_wall_ratio:
            hard_failures.append(
                {
                    "student": name,
                    "reason": "wall_and_median_wall_ratio_above_target",
                    "wall_cost_ratio": wall,
                    "median_paired_wall_cost_ratio": median_wall,
                }
            )
        elif wall > max_wall_ratio:
            warnings.append({"student": name, "reason": "aggregate_wall_ratio_above_target", "wall_cost_ratio": wall})
        if token > max_token_ratio:
            hard_failures.append({"student": name, "reason": "token_ratio_above_target", "token_cost_ratio": token})
    return {
        "passed": not hard_failures,
        "hard_failures": hard_failures,
        "warnings": warnings,
    }


def _pre_flash_warnings(pre_flash: dict[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    checks = pre_flash.get("checks", [])
    for check in checks if isinstance(checks, list) else []:
        if not isinstance(check, dict):
            continue
        details = check.get("details", {})
        details = details if isinstance(details, dict) else {}
        warning_reasons = details.get("warning_reasons", [])
        if warning_reasons:
            warnings.append(
                {
                    "reason": "pre_flash_check_warning",
                    "check": check.get("name", ""),
                    "warning_reasons": warning_reasons,
                }
            )
    return warnings


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _next_actions(blockers: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    reasons = {str(item.get("reason") or "") for item in blockers}
    warning_reasons = {str(item.get("reason") or "") for item in warnings}
    if "teacher_reference_suite_below_launch_target" in reasons:
        actions.append("Expand GPT-5.5 direct teacher reference to 8-12 fixed public tasks before public launch.")
    if "cost_gate_failed" in reasons or "aggregate_wall_ratio_above_target" in warning_reasons:
        actions.append("Keep quality gate fixed and slim lane-specific phase/context cost, starting with Pro aggregate wall ratio.")
    if "teacher_reference_gate_failed" in reasons:
        actions.append("Inspect failing teacher/student overlap rows before running more expensive A/B.")
    if "pre_flash_gate_failed" in reasons:
        actions.append("Fix deterministic Nexus contract gates before any Flash/Pro benchmark rerun.")
    if not actions:
        actions.append("Prepare public report and commit launch-candidate artifacts.")
    return actions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Combine P90 teacher quality, Nexus gates, and cost discipline into the P110 launch-candidate gate.")
    parser.add_argument("--repo-root", default=".", type=Path)
    parser.add_argument("--teacher-run", required=True, type=Path)
    parser.add_argument("--teacher-arm", default="without_nexus", choices=["with_nexus", "without_nexus"])
    parser.add_argument("--student", action="append", default=[], help="NAME=RUN_DIR")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--target-teacher-tasks", type=int, default=8)
    parser.add_argument("--min-overlap-tasks", type=int, default=4)
    args = parser.parse_args(argv)

    students: dict[str, Path] = {}
    for item in args.student:
        if "=" not in item:
            raise SystemExit(f"invalid --student: {item}")
        name, run_dir = item.split("=", 1)
        students[name] = Path(run_dir)
    payload = build_p110_launch_candidate_gate(
        repo_root=args.repo_root.resolve(),
        teacher_run=args.teacher_run,
        teacher_arm=args.teacher_arm,
        student_runs=students,
        target_teacher_tasks=args.target_teacher_tasks,
        min_overlap_tasks=args.min_overlap_tasks,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0 if payload.get("launch_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
