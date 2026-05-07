from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


def _load_tasks(path: Path, max_tasks: int) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks") if isinstance(payload, dict) else payload
    if not isinstance(tasks, list):
        raise SystemExit("tasks file must contain a list or {'tasks': [...]}")
    out: list[str] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("task_id") or task.get("id") or "")
        if task_id:
            out.append(task_id)
        if len(out) >= max_tasks:
            break
    return out


def _base_command(args: argparse.Namespace, *, output_dir: Path, task_ids: list[str], preflight_only: bool) -> list[str]:
    cmd = [
        "uv",
        "run",
        "python",
        "scripts/bench/capability_ab_runner.py",
        "--tasks-file",
        str(args.tasks_file),
        "--task-id-filter",
        ",".join(task_ids),
        "--output-dir",
        str(output_dir),
        "--max-tasks",
        str(len(task_ids)),
        "--repeat-trials",
        str(args.repeat_trials),
        "--timeout-sec",
        str(args.timeout_sec),
        "--per-task-stop-loss-sec",
        str(args.per_task_stop_loss_sec),
        "--total-timeout-sec",
        str(args.total_timeout_sec),
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
        str(args.model_name),
        "--enable-autoreason-executor",
        "--enable-ddtree-executor",
        "--enable-ultra-review-dry-gate",
        "--llm-candidate-cap",
        "3",
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
    if preflight_only:
        cmd.append("--preflight-only")
    return cmd


def _env(model_name: str) -> dict[str, str]:
    return {
        "NEXUS_VALUE_HIDDEN_VERIFIER": "1",
        "NEXUS_GEMINI_MODEL_NAME": model_name,
        "NEXUS_DIRECT_GEMINI_MODEL": model_name,
        "NEXUS_GATEWAY_COMPACT_PROMPT": "1",
        "NEXUS_GATEWAY_PROMPT_TRANSPORT": "stdin",
    }


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    task_ids = _load_tasks(Path(args.tasks_file), int(args.max_tasks))
    root = Path(args.output_dir)
    return {
        "schema_version": "nexus_weak_model_long_loop_v1",
        "model_name": str(args.model_name),
        "tasks_file": str(args.tasks_file),
        "task_ids": task_ids,
        "fail_fast": "stop_after_first_nonzero_task_return_code",
        "preflight_command": _base_command(args, output_dir=root / "preflight", task_ids=task_ids, preflight_only=True),
        "task_commands": [
            {
                "task_id": task_id,
                "output_dir": str(root / task_id),
                "command": _base_command(args, output_dir=root / task_id, task_ids=[task_id], preflight_only=False),
            }
            for task_id in task_ids
        ],
    }


def run_plan(plan: dict[str, Any], *, model_name: str, plan_only: bool) -> dict[str, Any]:
    env = {**_env(model_name)}
    results: list[dict[str, Any]] = []
    if plan_only:
        return {**plan, "execution_status": "plan_only", "results": results}
    preflight = subprocess.run(plan["preflight_command"], env={**env}, check=False)
    if preflight.returncode != 0:
        return {**plan, "execution_status": "preflight_failed", "preflight_returncode": preflight.returncode, "results": results}
    for item in plan["task_commands"]:
        result = subprocess.run(item["command"], env={**env}, check=False)
        row = {"task_id": item["task_id"], "returncode": result.returncode, "output_dir": item["output_dir"]}
        results.append(row)
        if result.returncode != 0:
            return {**plan, "execution_status": "stopped_on_failed_task", "failed_task_id": item["task_id"], "results": results}
    return {**plan, "execution_status": "complete", "results": results}


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Nexus Weak Model Long Loop",
        "",
        f"- model_name: `{payload['model_name']}`",
        f"- tasks_file: `{payload['tasks_file']}`",
        f"- task_count: `{len(payload['task_ids'])}`",
        f"- execution_status: `{payload.get('execution_status', 'not_run')}`",
        f"- fail_fast: `{payload['fail_fast']}`",
        "",
        "## Tasks",
        "",
    ]
    for task_id in payload["task_ids"]:
        lines.append(f"- `{task_id}`")
    if payload.get("results"):
        lines.extend(["", "## Results", ""])
        for row in payload["results"]:
            lines.append(f"- `{row['task_id']}`: returncode={row['returncode']} output={row['output_dir']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run weak-model Nexus tasks one by one and stop on the first failed task.")
    parser.add_argument("--tasks-file", default="scripts/bench/public_benchmark_nexus_value_v1.json")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model-name", default="gemini-3-flash-preview")
    parser.add_argument("--max-tasks", type=int, default=12)
    parser.add_argument("--repeat-trials", type=int, default=1)
    parser.add_argument("--timeout-sec", type=int, default=300)
    parser.add_argument("--per-task-stop-loss-sec", type=int, default=600)
    parser.add_argument("--total-timeout-sec", type=int, default=7200)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--output", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)

    result = run_plan(build_plan(args), model_name=str(args.model_name), plan_only=bool(args.plan_only))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(result), encoding="utf-8")
    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0 if result["execution_status"] in {"plan_only", "complete"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
