#!/usr/bin/env python3
"""
Sequential Fusion Trial v1 — A/B/C Sidecar Experiment
=====================================================
Group A (baseline): Qwen 7b planning + Qwen 14b patch only
Group B (Gemma sidecar): Gemma 12B planning/diagnosis + Qwen 14b patch
Group C (DeepSeek-R1 sidecar): DeepSeek-R1 14B planning/diagnosis + Qwen 14b patch

Usage:
    python3 sequential_fusion_trial_v1.py --group A --tasks 12
    python3 sequential_fusion_trial_v1.py --group B --tasks 12
    python3 sequential_fusion_trial_v1.py --group C --tasks 12
    python3 sequential_fusion_trial_v1.py --all --tasks 12
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

NEXUS_ROOT = Path(__file__).parent.parent.parent.resolve()
LOCAL_HEAL_ROOT = Path(os.environ.get("NEXUS_LOCAL_HEAL_ROOT_DIR", str(NEXUS_ROOT))).resolve()

# Task selection: 12 tasks mixing solved/unsolved/env-fail
SELECTED_TASKS = [
    # Previously solved (should solve again)
    ("psf__requests-2317", "requests", "python-default"),
    ("psf__requests-2931", "requests", "python-default"),
    ("django__django-11099", "django", "django-legacy"),
    ("sympy__sympy-13798", "sympy", "sympy-default"),
    ("sympy__sympy-13480", "sympy", "sympy-default"),
    ("astropy__astropy-14365", "astropy", "astropy-legacy"),
    # Previously unsolved (may or may not solve)
    ("astropy__astropy-12907", "astropy", "astropy-legacy"),
    ("astropy__astropy-13236", "astropy", "astropy-legacy"),
    ("astropy__astropy-13579", "astropy", "astropy-legacy"),
    ("sympy__sympy-12481", "sympy", "sympy-default"),
    ("sympy__sympy-13372", "sympy", "sympy-default"),
    ("astropy__astropy-14182", "astropy", "astropy-legacy"),
]

GROUP_CONFIGS = {
    "A": {
        "name": "baseline",
        "sidecar_enabled": "0",
        "sidecar_model": "",
        "description": "Qwen 7b planning + Qwen 14b patch only",
    },
    "B": {
        "name": "gemma_sidecar",
        "sidecar_enabled": "1",
        "sidecar_model": "gemma4-coder-12b-q4km",
        "description": "Gemma 12B planning/diagnosis + Qwen 14b patch",
    },
    "C": {
        "name": "deepseek_sidecar",
        "sidecar_enabled": "1",
        "sidecar_model": "deepseek-r1-14b-q4km",
        "description": "DeepSeek-R1 14B planning/diagnosis + Qwen 14b patch",
    },
}


def run_task(instance_id: str, family: str, env_profile: str, group: str, config: dict) -> dict:
    """Run a single task with the given group configuration."""
    print(f"\n{'='*60}")
    print(f"  Task: {instance_id} | Group: {group} ({config['name']})")
    print(f"  Sidecar: {config['sidecar_model'] or 'none'}")
    print(f"{'='*60}")

    env = os.environ.copy()
    env["NEXUS_SIDECAR_ENABLED"] = config["sidecar_enabled"]
    if config["sidecar_model"]:
        env["NEXUS_SIDECAR_MODEL"] = config["sidecar_model"]
    env["NEXUS_RUN_GROUP"] = group

    cmd = [
        sys.executable,
        str(NEXUS_ROOT / "benchmarking/swebench_lite/swe_local_heal.py"),
        "--instance_id", instance_id,
        "--output", str(NEXUS_ROOT / f"benchmarking/swebench_lite/sequential_fusion_v1_{group}.jsonl"),
    ]

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            env=env,
            cwd=str(NEXUS_ROOT),
            capture_output=True,
            text=True,
            timeout=900,  # 15 min timeout per task
        )
        wall_time = time.time() - start_time

        # Parse output for success/failure
        stdout = result.stdout
        stderr = result.stderr
        solved = "SUCCESS: Solve eligible!" in stdout

        return {
            "instance_id": instance_id,
            "group": group,
            "sidecar_model": config["sidecar_model"],
            "solved": solved,
            "wall_time_sec": round(wall_time, 1),
            "return_code": result.returncode,
            "stdout_tail": stdout[-500:] if stdout else "",
            "stderr_tail": stderr[-500:] if stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {
            "instance_id": instance_id,
            "group": group,
            "sidecar_model": config["sidecar_model"],
            "solved": False,
            "wall_time_sec": 900,
            "return_code": -1,
            "error": "TIMEOUT",
        }
    except Exception as e:
        return {
            "instance_id": instance_id,
            "group": group,
            "sidecar_model": config["sidecar_model"],
            "solved": False,
            "wall_time_sec": round(time.time() - start_time, 1),
            "return_code": -2,
            "error": str(e),
        }


def run_group(group: str, num_tasks: int) -> list[dict]:
    """Run all tasks for a given group."""
    config = GROUP_CONFIGS[group]
    print(f"\n{'#'*60}")
    print(f"  Sequential Fusion Trial v1 — Group {group}: {config['description']}")
    print(f"  Tasks: {num_tasks}")
    print(f"{'#'*60}")

    results = []
    tasks = SELECTED_TASKS[:num_tasks]

    for i, (instance_id, family, env_profile) in enumerate(tasks):
        print(f"\n[{i+1}/{len(tasks)}] Running {instance_id}...")
        result = run_task(instance_id, family, env_profile, group, config)
        results.append(result)

        # Save intermediate results
        out_path = NEXUS_ROOT / f"benchmarking/swebench_lite/sequential_fusion_v1_results_{group}.json"
        out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))

        status = "✅ SOLVED" if result["solved"] else "❌ FAILED"
        print(f"  {status} | {result['wall_time_sec']}s")

    return results


def print_summary(all_results: dict[str, list[dict]]):
    """Print comparison summary across groups."""
    print(f"\n{'#'*60}")
    print("  SEQUENTIAL FUSION TRIAL v1 — SUMMARY")
    print(f"{'#'*60}")

    for group, results in all_results.items():
        config = GROUP_CONFIGS[group]
        solved = sum(1 for r in results if r["solved"])
        total = len(results)
        avg_time = sum(r["wall_time_sec"] for r in results) / total if total else 0
        print(f"\n  Group {group} ({config['name']}):")
        print(f"    Solve rate: {solved}/{total} ({100*solved/total:.1f}%)")
        print(f"    Avg time: {avg_time:.1f}s")

    # Cross-group comparison
    if len(all_results) >= 2:
        print(f"\n  Cross-group comparison:")
        groups = list(all_results.keys())
        for i in range(len(groups)):
            for j in range(i+1, len(groups)):
                g1, g2 = groups[i], groups[j]
                r1, r2 = all_results[g1], all_results[g2]
                s1 = sum(1 for r in r1 if r["solved"])
                s2 = sum(1 for r in r2 if r["solved"])
                t1 = len(r1)
                t2 = len(r2)
                print(f"    {g1} vs {g2}: {s1}/{t1} vs {s2}/{t2}")

    # Task-level comparison
    print(f"\n  Task-level results:")
    print(f"  {'Task':<40} {'A':^6} {'B':^6} {'C':^6}")
    print(f"  {'-'*40} {'-'*6} {'-'*6} {'-'*6}")

    # Get all unique task IDs
    all_tasks = set()
    for results in all_results.values():
        for r in results:
            all_tasks.add(r["instance_id"])

    for task_id in sorted(all_tasks):
        row = f"  {task_id:<40}"
        for group in ["A", "B", "C"]:
            if group in all_results:
                result = next((r for r in all_results[group] if r["instance_id"] == task_id), None)
                if result:
                    cell = "✅" if result["solved"] else "❌"
                else:
                    cell = "--"
            else:
                cell = "--"
            row += f" {cell:^6}"
        print(row)


def main():
    parser = argparse.ArgumentParser(description="Sequential Fusion Trial v1")
    parser.add_argument("--group", choices=["A", "B", "C"], help="Run specific group")
    parser.add_argument("--all", action="store_true", help="Run all groups sequentially")
    parser.add_argument("--tasks", type=int, default=12, help="Number of tasks to run")
    parser.add_argument("--summary", action="store_true", help="Print summary from existing results")
    args = parser.parse_args()

    if args.summary:
        # Load existing results
        all_results = {}
        for group in ["A", "B", "C"]:
            result_path = NEXUS_ROOT / f"benchmarking/swebench_lite/sequential_fusion_v1_results_{group}.json"
            if result_path.exists():
                all_results[group] = json.loads(result_path.read_text())
        if all_results:
            print_summary(all_results)
        else:
            print("No results found. Run the experiment first.")
        return

    if not args.group and not args.all:
        parser.print_help()
        return

    groups_to_run = ["A", "B", "C"] if args.all else [args.group]
    all_results = {}

    for group in groups_to_run:
        results = run_group(group, args.tasks)
        all_results[group] = results

    print_summary(all_results)


if __name__ == "__main__":
    main()
