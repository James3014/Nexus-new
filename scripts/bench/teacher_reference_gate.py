from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def build_teacher_reference_gate(
    *,
    teacher_run: Path,
    student_runs: dict[str, Path],
    teacher_arm: str = "without_nexus",
    min_quality_ratio: float = 0.9,
    min_overlap_tasks: int = 4,
) -> dict[str, Any]:
    teacher_rows = _load_arm_rows(teacher_run, teacher_arm)
    teacher_by_task = _aggregate_by_task(teacher_rows)
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    student_payloads: list[dict[str, Any]] = []
    teacher_verified_rate = _verified_rate(teacher_by_task)

    if len(teacher_by_task) < min_overlap_tasks:
        failures.append(
            {
                "reason": "teacher_reference_too_small",
                "teacher_tasks": len(teacher_by_task),
                "min_overlap_tasks": min_overlap_tasks,
            }
        )

    for name, run_dir in student_runs.items():
        student_rows = _load_arm_rows(run_dir, "with_nexus")
        student_by_task = _aggregate_by_task(student_rows)
        overlap = sorted(set(teacher_by_task) & set(student_by_task))
        overlap_teacher = {task_id: teacher_by_task[task_id] for task_id in overlap}
        overlap_student = {task_id: student_by_task[task_id] for task_id in overlap}
        student_verified_rate = _verified_rate(overlap_student)
        target_rate = min_quality_ratio * teacher_verified_rate
        public_gate = _public_claim_gate(run_dir)
        trust_mismatch_count = sum(1 for row in overlap_student.values() if _trust_mismatch(row))
        record = {
            "student": name,
            "run_dir": str(run_dir),
            "overlap_tasks": len(overlap),
            "teacher_verified_rate": round(teacher_verified_rate, 4),
            "student_verified_rate": round(student_verified_rate, 4),
            "required_student_verified_rate": round(target_rate, 4),
            "student_verified_close_to_teacher": student_verified_rate >= target_rate,
            "student_verified_delta_vs_teacher": round(student_verified_rate - teacher_verified_rate, 4),
            "trust_mismatch_count": trust_mismatch_count,
            "public_claim_gate": public_gate.get("verdict", ""),
            "public_claim_checks": _public_claim_summary(public_gate),
        }
        student_payloads.append(record)
        if len(overlap) < min_overlap_tasks:
            failures.append(
                {
                    "reason": "student_teacher_overlap_too_small",
                    "student": name,
                    "overlap_tasks": len(overlap),
                    "min_overlap_tasks": min_overlap_tasks,
                }
            )
        if not record["student_verified_close_to_teacher"]:
            failures.append(
                {
                    "reason": "student_quality_below_teacher_threshold",
                    "student": name,
                    "student_verified_rate": record["student_verified_rate"],
                    "required_student_verified_rate": record["required_student_verified_rate"],
                }
            )
        if trust_mismatch_count:
            failures.append({"reason": "student_trust_mismatch", "student": name, "count": trust_mismatch_count})
        if record["public_claim_gate"] != "PASS":
            failures.append({"reason": "student_public_claim_gate_not_pass", "student": name})
        wall_ratio = float(record["public_claim_checks"].get("wall_cost_ratio") or 0.0)
        if wall_ratio > 1.8:
            warnings.append(
                {
                    "reason": "student_wall_ratio_above_target",
                    "student": name,
                    "wall_cost_ratio": wall_ratio,
                    "target": 1.8,
                }
            )

    return {
        "schema_version": "nexus_teacher_reference_gate.v1",
        "passed": not failures,
        "teacher_run": str(teacher_run),
        "teacher_arm": teacher_arm,
        "teacher_tasks": len(teacher_by_task),
        "teacher_verified_rate": round(teacher_verified_rate, 4),
        "min_quality_ratio": min_quality_ratio,
        "min_overlap_tasks": min_overlap_tasks,
        "students": student_payloads,
        "warnings": warnings,
        "failures": failures,
    }


def _load_arm_rows(run_dir: Path, arm: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(run_dir.glob(f"{arm}_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
    return rows


def _aggregate_by_task(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        task_id = str(row.get("task_id") or "")
        if task_id:
            grouped.setdefault(task_id, []).append(row)
    return {task_id: _aggregate_rows(task_rows) for task_id, task_rows in grouped.items()}


def _aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    verified = any(_verified(row) for row in rows)
    trust_mismatch = any(_trust_mismatch(row) for row in rows)
    return {
        "task_id": str(rows[-1].get("task_id") or ""),
        "verified": verified,
        "trust_mismatch": trust_mismatch,
        "trial_count": len(rows),
        "avg_wall_sec": round(sum(float(row.get("wall_duration_sec") or 0.0) for row in rows) / max(1, len(rows)), 4),
        "avg_tokens": round(sum(float(row.get("total_tokens") or 0.0) for row in rows) / max(1, len(rows)), 4),
    }


def _verified(row: dict[str, Any]) -> bool:
    return str(row.get("semantic_status") or "") == "VERIFIED" and not _trust_mismatch(row)


def _trust_mismatch(row: dict[str, Any]) -> bool:
    return bool(row.get("report_trust_mismatch", False))


def _verified_rate(rows_by_task: dict[str, dict[str, Any]]) -> float:
    if not rows_by_task:
        return 0.0
    return sum(1 for row in rows_by_task.values() if row.get("verified") is True) / len(rows_by_task)


def _public_claim_gate(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "evidence_bundle.json"
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"verdict": "MISSING", "checks": {}}
    gate = bundle.get("public_claim_gate", {})
    return gate if isinstance(gate, dict) else {"verdict": "", "checks": {}}


def _public_claim_summary(gate: dict[str, Any]) -> dict[str, Any]:
    checks = gate.get("checks", {})
    checks = checks if isinstance(checks, dict) else {}
    return {
        "with_semantic_verified_rate": checks.get("with_semantic_verified_rate"),
        "without_semantic_verified_rate": checks.get("without_semantic_verified_rate"),
        "trust_mismatch_free": checks.get("trust_mismatch_free"),
        "wall_cost_ratio": checks.get("wall_cost_ratio_with_over_without"),
        "median_paired_wall_cost_ratio": checks.get("median_paired_wall_cost_ratio_with_over_without"),
        "token_cost_ratio": checks.get("token_cost_ratio_with_over_without"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate weak-model Nexus runs against a GPT-5.5 direct reference.")
    parser.add_argument("--teacher-run", required=True)
    parser.add_argument("--teacher-arm", default="without_nexus", choices=["with_nexus", "without_nexus"])
    parser.add_argument("--student", action="append", default=[], help="NAME=RUN_DIR")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    students: dict[str, Path] = {}
    for item in args.student:
        if "=" not in item:
            raise SystemExit(f"invalid --student: {item}")
        name, run_dir = item.split("=", 1)
        students[name] = Path(run_dir)
    payload = build_teacher_reference_gate(
        teacher_run=Path(args.teacher_run),
        teacher_arm=str(args.teacher_arm),
        student_runs=students,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
