from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TaskArm:
    task_id: str
    task_type: str
    category: str
    status: str
    semantic_status: str
    trust_mismatch: bool
    wall_sec: float
    tokens: int
    model_calls: float
    run_eligible: bool
    infra_invalid_reason: str
    model_uses_nexus: bool
    gemini_uses_nexus: bool
    nexus_wearing_valid: bool
    nexus_winner_source: str
    baseline_source_policy: str
    rescue_cost_status: str
    token_capture_status: str
    selected_count: int
    strategy_path: str
    high_cost_selected: tuple[str, ...]

    @property
    def verified(self) -> bool:
        return self.semantic_status == "VERIFIED" and not self.trust_mismatch

    @property
    def success_source(self) -> str:
        if not self.verified:
            return "failed"
        source_text = " ".join(
            [
                self.nexus_winner_source,
                self.baseline_source_policy,
                self.rescue_cost_status,
                self.token_capture_status,
            ]
        ).lower()
        if (
            "local_hidden_contract_fast_path" in source_text
            or self.baseline_source_policy == "hidden_contract_local_first_before_llm"
        ):
            return "local_deterministic_success"
        if self.model_calls > 0 and (self.model_uses_nexus or self.gemini_uses_nexus or self.nexus_wearing_valid):
            return "model_assisted_success"
        if self.model_calls <= 0:
            return "nexus_tool_success"
        return "verified_non_model_success"

    @property
    def model_uplift_eligible(self) -> bool:
        return (
            self.verified
            and self.run_eligible
            and not self.infra_invalid_reason
            and self.model_calls > 0
            and (self.model_uses_nexus or self.gemini_uses_nexus or self.nexus_wearing_valid)
        )


def _row_files(run_dir: Path, arm: str) -> list[Path]:
    return sorted(run_dir.glob(f"evidence_*/*{arm}*.row.json"))


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_list(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return ()


def _load_arm_rows(run_dir: Path, arm: str) -> dict[str, TaskArm]:
    out: dict[str, TaskArm] = {}
    for path in _row_files(run_dir, arm):
        row = json.loads(path.read_text(encoding="utf-8"))
        task_id = str(row.get("task_id") or "")
        if not task_id:
            continue
        out[task_id] = TaskArm(
            task_id=task_id,
            task_type=str(row.get("task_type") or ""),
            category=str(row.get("category") or ""),
            status=str(row.get("status") or ""),
            semantic_status=str(row.get("semantic_status") or ""),
            trust_mismatch=bool(row.get("report_trust_mismatch", False)),
            wall_sec=_as_float(row.get("wall_duration_sec")),
            tokens=_as_int(row.get("total_tokens")),
            model_calls=_as_float(row.get("model_calls")),
            run_eligible=bool(row.get("run_eligible", True)),
            infra_invalid_reason=str(row.get("infra_invalid_reason") or ""),
            model_uses_nexus=bool(row.get("model_uses_nexus", False)),
            gemini_uses_nexus=bool(row.get("gemini_uses_nexus", False)),
            nexus_wearing_valid=bool(row.get("nexus_wearing_valid", False)),
            nexus_winner_source=str(row.get("nexus_winner_source") or row.get("source") or ""),
            baseline_source_policy=str(row.get("baseline_source_policy") or ""),
            rescue_cost_status=str(row.get("rescue_cost_status") or ""),
            token_capture_status=str(row.get("token_capture_status") or ""),
            selected_count=_as_int(row.get("route_decision_selected_count")),
            strategy_path=str(row.get("strategy_path") or ""),
            high_cost_selected=_as_list(row.get("route_profile_high_cost_selected")),
        )
    return out


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _fmt_ratio(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}x"


def _bucket(row: TaskArm) -> str:
    text = f"{row.task_id} {row.task_type} {row.category}".lower()
    if "repair" in text:
        return "repair"
    if "gov" in text or "governance" in text or "refactor" in text:
        return "governance"
    if "claim" in text or "api" in text or "external" in text:
        return "external_claim"
    if "cross" in text or "module" in text:
        return "cross_module"
    if "rlm" in text or "long" in text:
        return "long_horizon"
    return "hidden"


def _recommendation(*, student: TaskArm, teacher: TaskArm, student_bare: TaskArm | None, teacher_direct: TaskArm | None) -> str:
    wall_ratio = _ratio(student.wall_sec, teacher.wall_sec)
    token_ratio = _ratio(float(student.tokens), float(teacher.tokens))
    teacher_direct_failed = bool(teacher_direct and not teacher_direct.verified)
    student_bare_failed = bool(student_bare and not student_bare.verified)

    if student.verified and not student.model_uplift_eligible:
        if student.success_source == "local_deterministic_success":
            return "keep_as_nexus_cost_avoidance_not_model_uplift"
        return "separate_nexus_tool_success_from_model_uplift"
    if not student.verified and teacher.verified:
        return "raise_student_capability_or_context"
    if student.trust_mismatch:
        return "fix_trust_before_cost"
    if teacher_direct_failed and teacher.verified and student.verified:
        if wall_ratio and wall_ratio >= 2.0:
            return "keep_nexus_value_but_copy_teacher_runtime_profile"
        return "keep_profile_nexus_value_confirmed"
    if student_bare_failed and student.verified:
        if wall_ratio and wall_ratio >= 2.0:
            return "nexus_required_but_student_runtime_too_heavy"
        return "promote_student_profile"
    if wall_ratio and wall_ratio >= 2.0:
        return "slim_student_runtime_path"
    if token_ratio and token_ratio > 1.5:
        return "compact_student_context"
    return "near_teacher"


def build_gap_matrix(
    *,
    student_run: Path,
    teacher_run: Path,
    student_name: str,
    teacher_name: str,
    teacher_arm: str = "with_nexus",
) -> dict[str, Any]:
    if teacher_arm not in {"with_nexus", "without_nexus"}:
        raise ValueError(f"unsupported_teacher_arm:{teacher_arm}")
    student = _load_arm_rows(student_run, "with_nexus")
    student_bare = _load_arm_rows(student_run, "without_nexus")
    teacher = _load_arm_rows(teacher_run, teacher_arm)
    teacher_direct = _load_arm_rows(teacher_run, "without_nexus")
    task_ids = sorted(set(student) & set(teacher))
    rows: list[dict[str, Any]] = []
    for task_id in task_ids:
        s = student[task_id]
        t = teacher[task_id]
        sb = student_bare.get(task_id)
        td = teacher_direct.get(task_id)
        wall_ratio = _ratio(s.wall_sec, t.wall_sec)
        token_ratio = _ratio(float(s.tokens), float(t.tokens))
        rows.append(
            {
                "task_id": task_id,
                "bucket": _bucket(s),
                "student_verified": s.verified,
                "teacher_verified": t.verified,
                "student_success_source": s.success_source,
                "teacher_success_source": t.success_source,
                "student_model_uplift_eligible": s.model_uplift_eligible,
                "teacher_model_uplift_eligible": t.model_uplift_eligible,
                "student_run_eligible": s.run_eligible,
                "teacher_run_eligible": t.run_eligible,
                "student_infra_invalid_reason": s.infra_invalid_reason,
                "teacher_infra_invalid_reason": t.infra_invalid_reason,
                "student_bare_verified": bool(sb and sb.verified),
                "teacher_direct_verified": bool(td and td.verified),
                "student_wall_sec": round(s.wall_sec, 4),
                "teacher_wall_sec": round(t.wall_sec, 4),
                "student_vs_teacher_wall_ratio": round(wall_ratio, 4) if wall_ratio is not None else None,
                "student_tokens": s.tokens,
                "teacher_tokens": t.tokens,
                "student_vs_teacher_token_ratio": round(token_ratio, 4) if token_ratio is not None else None,
                "student_selected_count": s.selected_count,
                "teacher_selected_count": t.selected_count,
                "student_strategy_path": s.strategy_path,
                "teacher_strategy_path": t.strategy_path,
                "student_high_cost_selected": list(s.high_cost_selected),
                "teacher_high_cost_selected": list(t.high_cost_selected),
                "recommendation": _recommendation(student=s, teacher=t, student_bare=sb, teacher_direct=td),
            }
        )
    by_bucket: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = str(row["bucket"])
        data = by_bucket.setdefault(bucket, {"task_count": 0, "recommendations": {}})
        data["task_count"] += 1
        recs = data["recommendations"]
        recs[row["recommendation"]] = recs.get(row["recommendation"], 0) + 1
    return {
        "schema_version": "nexus_teacher_student_gap_matrix_v1",
        "student_model": student_name,
        "teacher_model": teacher_name,
        "teacher_arm": teacher_arm,
        "student_run": str(student_run),
        "teacher_run": str(teacher_run),
        "rows": rows,
        "bucket_summary": by_bucket,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Nexus Teacher Student Gap Matrix",
        "",
        f"- student: `{payload['student_model']}`",
        f"- teacher: `{payload['teacher_model']}`",
        f"- teacher_arm: `{payload.get('teacher_arm', 'with_nexus')}`",
        "",
        "| Task | Bucket | Student | Teacher | Source | Eligible | Wall | Tokens | Strategy | Recommendation |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for row in payload["rows"]:
        lines.append(
            f"| {row['task_id']} | {row['bucket']} | "
            f"{'PASS' if row['student_verified'] else 'FAIL'} | "
            f"{'PASS' if row['teacher_verified'] else 'FAIL'} | "
            f"{row['student_success_source']} -> {row['teacher_success_source']} | "
            f"{row['student_model_uplift_eligible']} -> {row['teacher_model_uplift_eligible']} | "
            f"{row['student_wall_sec']:.2f}s / {row['teacher_wall_sec']:.2f}s ({_fmt_ratio(row['student_vs_teacher_wall_ratio'])}) | "
            f"{row['student_tokens']} / {row['teacher_tokens']} ({_fmt_ratio(row['student_vs_teacher_token_ratio'])}) | "
            f"{row['student_strategy_path']} -> {row['teacher_strategy_path']} | "
            f"{row['recommendation']} |"
        )
    lines.extend(["", "## Bucket Summary", ""])
    for bucket, data in sorted(payload["bucket_summary"].items()):
        lines.append(f"- `{bucket}`: {data['task_count']} task(s), recommendations={data['recommendations']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare weak-model Nexus traces against a selectable GPT-5.5 teacher arm.")
    parser.add_argument("--student-run", required=True)
    parser.add_argument("--teacher-run", required=True)
    parser.add_argument("--student-name", default="flash_nexus")
    parser.add_argument("--teacher-name", default="gpt55_nexus")
    parser.add_argument("--teacher-arm", choices=["with_nexus", "without_nexus"], default="with_nexus")
    parser.add_argument("--output", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)

    payload = build_gap_matrix(
        student_run=Path(args.student_run),
        teacher_run=Path(args.teacher_run),
        student_name=str(args.student_name),
        teacher_name=str(args.teacher_name),
        teacher_arm=str(args.teacher_arm),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(payload), encoding="utf-8")
    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
