import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import datasets
from nexus.services.local_heal.pipeline import HealPipeline, HealContext
from nexus.services.local_heal.task_manifest import (
    LocalHealTaskSpec,
    local_heal_20_task_manifest,
    local_heal_40_task_manifest,
)

NEXUS_ROOT = Path(__file__).parent.parent.parent.resolve()


def build_result_row(task: dict[str, Any], res_ctx: HealContext) -> dict[str, Any]:
    return {
        "instance_id": task["instance_id"],
        "manifest_task_id": task.get("manifest_task_id", ""),
        "env_profile": task.get("env_profile", "python-default"),
        "model_patch": res_ctx.final_patch,
        "model_name_or_path": "nexus-local-heal-v17",
        "solve_eligible": res_ctx.solve_eligible,
        "failure_reason": failure_reason_for_result(res_ctx),
        "receipt_path": str(res_ctx.receipt_path),
        "wall_time_sec_measured": res_ctx.wall_time_sec,
        "token_telemetry_status": res_ctx.token_telemetry_status,
        "token_total_estimated": res_ctx.token_total_estimated,
    }


def build_task_from_spec(
    spec: LocalHealTaskSpec,
    dataset: Any,
    *,
    root_dir: Path,
) -> dict[str, Any]:
    if spec.kind == "swebench":
        instance = None
        if spec.swe_index is not None and spec.swe_index < len(dataset):
            instance = dataset[spec.swe_index]
        elif spec.instance_id:
            instance = next((row for row in dataset if row["instance_id"] == spec.instance_id), None)
            
        if not instance:
            raise ValueError(f"Task {spec.task_id} not found in dataset")

        return {
            "instance_id": instance["instance_id"],
            "manifest_task_id": spec.task_id,
            "repo_dir": root_dir,
            "problem_statement": instance["problem_statement"],
            "env_profile": spec.env_profile,
            "expected_stop_layer": spec.expected_stop_layer,
            "expected_reason_family": spec.expected_reason_family,
            "probe_goal": spec.probe_goal,
            "local_mode": False,
        }

    local_file = root_dir / spec.local_path
    return {
        "instance_id": f"local_fix_{local_file.name}",
        "manifest_task_id": spec.task_id,
        "repo_dir": root_dir,
        "local_path": local_file,
        "env_profile": spec.env_profile,
        "problem_statement": f"Fix race condition in {local_file.name}",
        "expected_stop_layer": spec.expected_stop_layer,
        "expected_reason_family": spec.expected_reason_family,
        "probe_goal": spec.probe_goal,
        "local_mode": True,
    }


def build_tasks_from_manifest_specs(
    specs: tuple[LocalHealTaskSpec, ...],
    dataset: Any,
    *,
    root_dir: Path,
) -> list[dict[str, Any]]:
    tasks = []
    for spec in specs:
        tasks.append(
            build_task_from_spec(
                spec,
                dataset,
                root_dir=root_dir,
            )
        )
    return tasks


def build_tasks_from_manifest(
    manifest_name: str,
    dataset: Any,
    *,
    root_dir: Path = NEXUS_ROOT,
) -> list[dict[str, Any]]:
    from nexus.services.local_heal.task_manifest import (
        local_heal_20_task_manifest,
        local_heal_40_task_manifest,
        local_heal_60_task_manifest,
        local_heal_100_task_manifest,
        local_heal_113_task_manifest,
    )
    if manifest_name == "local-heal-20":
        specs = local_heal_20_task_manifest()
    elif manifest_name == "local-heal-40":
        specs = local_heal_40_task_manifest()
    elif manifest_name == "local-heal-60":
        specs = local_heal_60_task_manifest()
    elif manifest_name == "local-heal-100":
        specs = local_heal_100_task_manifest()
    elif manifest_name == "local-heal-113":
        specs = local_heal_113_task_manifest()
    else:
        raise ValueError(f"Unknown task manifest: {manifest_name}")
        
    return build_tasks_from_manifest_specs(
        specs,
        dataset=dataset,
        root_dir=root_dir,
    )


def localized_files_for_task(task: dict[str, Any]) -> list[tuple[str, str]]:
    if not task.get("local_mode"):
        return []

    local_path = Path(task["local_path"]).resolve()
    repo_dir = Path(task["repo_dir"]).resolve()
    try:
        relative_path = local_path.relative_to(repo_dir)
    except ValueError:
        relative_path = Path(local_path.name)
    return [
        (
            str(relative_path),
            local_path.read_text(encoding="utf-8", errors="replace"),
        )
    ]


def read_resume_task_ids(path: str | Path | None, *, mode: str) -> set[str]:
    if not path:
        return set()

    resume_path = Path(path)
    if not resume_path.exists():
        return set()

    completed = set()
    with open(resume_path, "r") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            tid = row.get("manifest_task_id")
            if not tid:
                continue

            if mode == "repair" and (row.get("solve_eligible") or row.get("failure_reason")):
                completed.add(tid)
            elif mode == "preflight" and (row.get("preflight_ready") or row.get("failure_reason")):
                completed.add(tid)
    return completed


def filter_tasks_for_resume(
    tasks: list[dict[str, Any]], completed_task_ids: set[str]
) -> list[dict[str, Any]]:
    return [
        task for task in tasks if task.get("manifest_task_id") not in completed_task_ids
    ]


def failure_reason_for_result(res_ctx: Any) -> str:
    explicit = str(getattr(res_ctx, "failure_reason", "") or "").strip()
    if explicit:
        return explicit

    if not getattr(res_ctx, "reproduced", True):
        return "REPRO_NOT_REPRODUCED"

    return "UNKNOWN_FAILURE"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--instance_id", type=str, help="Specific instance ID to run")
    parser.add_argument(
        "--local_path", type=str, help="Local file path to fix (skips dataset)"
    )
    parser.add_argument(
        "--task_manifest",
        choices=["local-heal-20", "local-heal-40", "local-heal-60", "local-heal-100", "local-heal-113"],
        help="Run a fixed local-heal task manifest",
    )
    parser.add_argument(
        "--preflight_only",
        action="store_true",
        help="Write readiness rows without cloning or invoking models",
    )
    parser.add_argument("--dataset", default="princeton-nlp/SWE-bench_Verified")
    parser.add_argument(
        "--output",
        default=str(NEXUS_ROOT / "benchmarking/swebench_lite/predictions_swe.jsonl"),
    )
    parser.add_argument(
        "--resume_from",
        type=str,
        help="JSONL ledger whose completed manifest task IDs should be skipped",
    )
    parser.add_argument(
        "--hidden_verifier", action="store_true", help="Enable hidden verifier check"
    )
    parser.add_argument(
        "--repro_script_file",
        type=str,
        help="Optional existing repro script to use instead of generating one",
    )

    args = parser.parse_args()

    dataset = None
    if not args.local_path:
        print(f"📦 Loading {args.dataset}...")
        dataset = datasets.load_dataset(args.dataset, split="test")

    tasks = []
    if args.local_path:
        tasks = [
            {
                "instance_id": f"local_fix_{Path(args.local_path).name}",
                "repo_dir": NEXUS_ROOT,
                "local_path": args.local_path,
                "env_profile": "python-default",
                "problem_statement": f"Fix issues in {args.local_path}",
                "local_mode": True,
            }
        ]
    elif args.instance_id:
        instance = next(
            (row for row in dataset if row["instance_id"] == args.instance_id), None
        )
        if not instance:
            print(f"❌ Error: Instance {args.instance_id} not found in dataset")
            return
        tasks = [
            {
                "instance_id": instance["instance_id"],
                "repo_dir": NEXUS_ROOT,
                "problem_statement": instance["problem_statement"],
                "env_profile": "python-default",
                "local_mode": False,
            }
        ]
    elif args.task_manifest:
        tasks = build_tasks_from_manifest(
            args.task_manifest, dataset, root_dir=NEXUS_ROOT
        )
        if args.resume_from:
            completed = read_resume_task_ids(
                args.resume_from, mode="preflight" if args.preflight_only else "repair"
            )
            tasks = filter_tasks_for_resume(tasks, completed)
        tasks = tasks[args.index : args.index + args.limit]
    else:
        tasks = [
            {
                "instance_id": row["instance_id"],
                "repo_dir": NEXUS_ROOT,
                "problem_statement": row["problem_statement"],
                "env_profile": "python-default",
                "local_mode": False,
            }
            for row in list(dataset)[args.index : args.index + args.limit]
        ]

    if not tasks:
        print("ℹ️ No tasks to process.")
        return

    from mock_gemini import ollama_generate

    pipeline = HealPipeline(
        ollama_generate_fn=ollama_generate, hidden_verifier=args.hidden_verifier
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    mode_label = "PREFLIGHT" if args.preflight_only else "REPAIR"
    print(f"\n🚀 Starting {mode_label} Loop for {len(tasks)} tasks...")

    with open(out_path, "a") as out_file:
        for i, task in enumerate(tasks):
            print(f"\n{'='*60}")
            print(
                f"[{i+1}/{len(tasks)}] Processing {task['instance_id']} (Profile: {task.get('env_profile')})"
            )

            start_wall = time.time()
            ctx = HealContext(
                instance_id=task["instance_id"],
                repo_dir=Path(task["repo_dir"]),
                problem_statement=task["problem_statement"],
                expected_stop_layer=task.get("expected_stop_layer", "verification"),
                expected_reason_family=task.get("expected_reason_family", "SOLVED"),
            )
            ctx.auto_heal_enabled = True
            ctx.python_executable = task.get("python_executable", "")
            ctx.local_mode = task.get("local_mode", False)
            if ctx.local_mode:
                ctx.local_path = Path(task["local_path"])
                ctx.localized_files = localized_files_for_task(task)

            if args.preflight_only:
                from nexus.services.local_heal.preflight import run_preflight_for_spec
                spec = LocalHealTaskSpec(
                    task_id=task.get("manifest_task_id", "manual"),
                    kind="local_concurrency" if task.get("local_mode") else "swebench",
                    family="concurrency" if task.get("local_mode") else "swebench",
                    env_profile=task.get("env_profile", "python-default"),
                    local_path=str(task.get("local_path", "")) if task.get("local_mode") else None,
                )
                preflight_row = run_preflight_for_spec(spec, Path(task["repo_dir"]))
                out_file.write(json.dumps(preflight_row) + "\n")
                out_file.flush()
                continue

            if args.repro_script_file:
                repro_path = Path(args.repro_script_file)
                if repro_path.exists():
                    ctx.repro_script = repro_path.read_text()

            try:
                res_ctx = pipeline.run(ctx)
                res_ctx.wall_time_sec = time.time() - start_wall
                res_ctx.token_telemetry_status = "estimated"

                if res_ctx.solve_eligible:
                    print("  ✅ SUCCESS: Solve eligible!")
                else:
                    is_np_error = "name 'np' is not defined" in str(
                        res_ctx.evaluation_report
                    ) or "name 'np' is not defined" in str(res_ctx.repro_evidence)
                    if (
                        res_ctx.failure_reason == "REPRO_ENVIRONMENT_FAILURE"
                        or not res_ctx.reproduced
                    ) and is_np_error:
                        print("  🔧 Auto-fixing repro script...")
                        res_ctx.repro_script = "import numpy as np\n" + res_ctx.repro_script
                        res_ctx = pipeline.run(res_ctx)

                row = build_result_row(task, res_ctx)
                out_file.write(json.dumps(row) + "\n")
                out_file.flush()
            except Exception as e:
                print(f"  💥 CRITICAL EXCEPTION: {e}")
                row = {
                    "instance_id": task["instance_id"],
                    "manifest_task_id": task.get("manifest_task_id", ""),
                    "solve_eligible": False,
                    "failure_reason": f"CRITICAL_EXCEPTION:{type(e).__name__}:{str(e)}",
                }
                out_file.write(json.dumps(row) + "\n")
                out_file.flush()

    print(f"\n✅ Predictions saved to: {out_path}")


if __name__ == "__main__":
    main()
