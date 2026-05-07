from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SweepProfile:
    name: str
    reason: str
    env: tuple[str, ...]
    args: tuple[str, ...]
    target_recommendations: tuple[str, ...]


PROFILES: tuple[SweepProfile, ...] = (
    SweepProfile(
        name="flash_compact_context",
        reason="Reduce prompt/context tokens while keeping always-on Nexus routing.",
        env=("NEXUS_GATEWAY_COMPACT_PROMPT=1", "NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin"),
        args=("--force-flow", "auto", "--always-on-eval", "--llm-candidate-cap", "3", "--nexus-only"),
        target_recommendations=("compact_student_context",),
    ),
    SweepProfile(
        name="flash_lite_route",
        reason="Shrink unnecessary runtime path while preserving the public-readiness candidate floor.",
        env=("NEXUS_GATEWAY_COMPACT_PROMPT=1", "NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin"),
        args=("--force-flow", "auto", "--always-on-eval", "--llm-candidate-cap", "3", "--nexus-only"),
        target_recommendations=("slim_student_runtime_path",),
    ),
    SweepProfile(
        name="flash_teacher_repair_copy",
        reason="Keep Nexus repair value but copy the teacher's shorter verified runtime profile.",
        env=(
            "NEXUS_GATEWAY_COMPACT_PROMPT=1",
            "NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin",
            "NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1",
            "NEXUS_RLM_REPAIR_LOOP=1",
        ),
        args=("--force-flow", "auto", "--always-on-eval", "--enable-llm-self-heal", "--llm-candidate-cap", "3", "--nexus-only"),
        target_recommendations=(
            "keep_nexus_value_but_copy_teacher_runtime_profile",
            "nexus_required_but_student_runtime_too_heavy",
        ),
    ),
)


def _load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _task_ids_for(profile: SweepProfile, rows: list[dict[str, Any]]) -> list[str]:
    task_ids = [
        str(row.get("task_id") or "")
        for row in rows
        if str(row.get("recommendation") or "") in set(profile.target_recommendations)
    ]
    return sorted(task_id for task_id in task_ids if task_id)


def _command_for(
    *,
    profile: SweepProfile,
    task_ids: list[str],
    tasks_file: str,
    output_dir: str,
    model_name: str,
    timeout_sec: int,
    total_timeout_sec: int,
) -> list[str]:
    cmd = [
        "uv",
        "run",
        "python",
        "scripts/bench/capability_ab_runner.py",
        "--tasks-file",
        tasks_file,
        "--task-id-filter",
        ",".join(task_ids),
        "--output-dir",
        f"{output_dir}/{profile.name}",
        "--max-tasks",
        str(len(task_ids)),
        "--repeat-trials",
        "1",
        "--timeout-sec",
        str(timeout_sec),
        "--per-task-stop-loss-sec",
        str(max(timeout_sec * 2, 300)),
        "--total-timeout-sec",
        str(total_timeout_sec),
        "--difficulty",
        "all",
        "--repo-kind-filter",
        "all",
        "--with-nexus-runner",
        "subprocess",
        "--with-llm-mode",
        "all",
        "--with-model-provider",
        "gemini",
        "--without-mode",
        "gemini",
        "--gemini-model",
        model_name,
        "--enable-autoreason-executor",
        "--enable-ddtree-executor",
        "--enable-ultra-review-dry-gate",
        "--force-learn-slo-ready",
        "--neutralize-history",
        "--disable-learning-loop",
        "--materialize-missing",
        "--isolation-mode",
        "preserve_target",
        "--evidence-bundle",
        "--markdown-report",
        "auto",
        "--progress-log",
    ]
    cmd.extend(profile.args)
    return cmd


def _shell_join(parts: list[str]) -> str:
    return " ".join(parts)


def _with_preflight(cmd: list[str]) -> list[str]:
    if "--preflight-only" in cmd:
        return list(cmd)
    return [*cmd, "--preflight-only"]


def build_sweep_plan(
    *,
    gap_payload: dict[str, Any],
    tasks_file: str,
    output_dir: str,
    model_name: str,
    timeout_sec: int,
    total_timeout_sec: int,
) -> dict[str, Any]:
    rows = list(gap_payload.get("rows", []) or [])
    profiles: list[dict[str, Any]] = []
    for profile in PROFILES:
        task_ids = _task_ids_for(profile, rows)
        if not task_ids:
            continue
        command = _command_for(
            profile=profile,
            task_ids=task_ids,
            tasks_file=tasks_file,
            output_dir=output_dir,
            model_name=model_name,
            timeout_sec=timeout_sec,
            total_timeout_sec=total_timeout_sec,
        )
        preflight_command = _with_preflight(command)
        env = [
            "NEXUS_VALUE_HIDDEN_VERIFIER=1",
            f"NEXUS_GEMINI_MODEL_NAME={model_name}",
            f"NEXUS_DIRECT_GEMINI_MODEL={model_name}",
            *profile.env,
        ]
        profiles.append(
            {
                "name": profile.name,
                "reason": profile.reason,
                "target_recommendations": list(profile.target_recommendations),
                "task_ids": task_ids,
                "env": env,
                "command": command,
                "preflight_command": preflight_command,
                "shell_command": _shell_join([*env, *command]),
                "preflight_shell_command": _shell_join([*env, *preflight_command]),
                "promotion_gate": {
                    "verified_must_not_drop": True,
                    "trust_mismatch_must_be_zero": True,
                    "wall_ratio_to_teacher_must_improve_pct": 15,
                    "token_ratio_to_teacher_must_improve_pct": 10,
                    "stop_on_first_failed_task": True,
                },
            }
        )
    return {
        "schema_version": "nexus_teacher_student_sweep_plan_v1",
        "student_model": str(gap_payload.get("student_model") or "flash_nexus"),
        "teacher_model": str(gap_payload.get("teacher_model") or "gpt55_nexus"),
        "tasks_file": tasks_file,
        "output_dir": output_dir,
        "model_name": model_name,
        "profiles": profiles,
        "closure_rule": (
            "Promote only profiles that keep verified delivery and reduce wall/token gap. "
            "If a profile fails one task, stop and inspect that task trace before continuing."
        ),
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Nexus Teacher Student Sweep Plan",
        "",
        f"- student: `{payload['student_model']}`",
        f"- teacher: `{payload['teacher_model']}`",
        f"- model_name: `{payload['model_name']}`",
        "",
        "## Profiles",
        "",
    ]
    if not payload["profiles"]:
        lines.append("- No actionable teacher-student gap recommendations were found.")
    for profile in payload["profiles"]:
        lines.extend(
            [
                f"### {profile['name']}",
                "",
                f"- reason: {profile['reason']}",
                f"- task_ids: `{','.join(profile['task_ids'])}`",
                f"- env: `{' '.join(profile['env'])}`",
                f"- preflight: `{profile['preflight_shell_command']}`",
                f"- command: `{profile['shell_command']}`",
                f"- gate: `{json.dumps(profile['promotion_gate'], sort_keys=True)}`",
                "",
            ]
        )
    lines.extend(["## Closure Rule", "", payload["closure_rule"], ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Flash+Nexus profile sweep commands from a teacher/student gap matrix.")
    parser.add_argument("--gap-json", required=True)
    parser.add_argument("--tasks-file", default="scripts/bench/public_benchmark_nexus_value_v1.json")
    parser.add_argument("--output-dir", default=".nexus/reports/bench_flash_teacher_sweep")
    parser.add_argument("--model-name", default="gemini-3-flash-preview")
    parser.add_argument("--timeout-sec", type=int, default=300)
    parser.add_argument("--total-timeout-sec", type=int, default=3600)
    parser.add_argument("--output", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)

    payload = build_sweep_plan(
        gap_payload=_load_payload(Path(args.gap_json)),
        tasks_file=str(args.tasks_file),
        output_dir=str(args.output_dir),
        model_name=str(args.model_name),
        timeout_sec=int(args.timeout_sec),
        total_timeout_sec=int(args.total_timeout_sec),
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
