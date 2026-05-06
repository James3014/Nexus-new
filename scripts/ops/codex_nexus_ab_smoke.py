#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_TASK_IDS = (
    "rlm-harder-v2-governance-001",
    "rlm-harder-v2-evidence-001",
    "rlm-harder-v2-belief-001",
    "rlm-harder-v2-memory-001",
)
MAX_PREFLIGHT_TASKS = 4


def benchmark_env(model: str) -> dict[str, str]:
    env = os.environ.copy()
    env["NEXUS_VALUE_HIDDEN_VERIFIER"] = "1"
    env["NEXUS_CODEX_MODEL_NAME"] = model
    env["NEXUS_DIRECT_CODEX_MODEL"] = model
    env["NEXUS_RLM_REPAIR_LOOP"] = "1"
    env["NEXUS_DIRECT_CODEX_TIMEOUT_SEC"] = "180"
    env["NEXUS_BENCH_GATEWAY_TIMEOUT_SEC"] = "240"
    existing_pythonpath = env.get("PYTHONPATH", "")
    repo_root = Path(__file__).resolve().parents[2]
    env["PYTHONPATH"] = str(repo_root) if not existing_pythonpath else f"{repo_root}{os.pathsep}{existing_pythonpath}"
    return env


def build_command(*, output_dir: str, task_ids: tuple[str, ...], preflight_only: bool) -> list[str]:
    cmd = [
        sys.executable,
        "scripts/bench/capability_ab_runner.py",
        "--tasks-file",
        "scripts/bench/public_benchmark_rlm_harder_v2.json",
        "--output-dir",
        output_dir,
        "--max-tasks",
        str(len(task_ids)),
        "--repeat-trials",
        "1",
        "--timeout-sec",
        "300",
        "--total-timeout-sec",
        "3600",
        "--stop-loss-sec",
        "3600",
        "--per-task-stop-loss-sec",
        "600",
        "--difficulty",
        "all",
        "--repo-kind-filter",
        "all",
        "--task-id-filter",
        ",".join(task_ids),
        "--force-flow",
        "hyper_sprint",
        "--with-nexus-runner",
        "subprocess",
        "--with-llm-mode",
        "all",
        "--with-model-provider",
        "codex",
        "--without-mode",
        "codex",
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


def validate_smoke_plan(*, cmd: list[str], env: dict[str, str], task_ids: tuple[str, ...]) -> dict[str, Any]:
    reasons: list[str] = []
    if len(task_ids) > MAX_PREFLIGHT_TASKS:
        reasons.append("task_count_exceeds_preflight_limit")
    if env.get("NEXUS_VALUE_HIDDEN_VERIFIER") != "1":
        reasons.append("hidden_verifier_disabled")
    if env.get("NEXUS_CODEX_MODEL_NAME") != env.get("NEXUS_DIRECT_CODEX_MODEL"):
        reasons.append("same_model_lock_missing")
    required_flags = (
        "--with-nexus-runner",
        "--with-llm-mode",
        "--without-mode",
        "--enable-autoreason-executor",
        "--enable-ddtree-executor",
        "--enable-ultra-review-dry-gate",
        "--evidence-bundle",
    )
    for flag in required_flags:
        if flag not in cmd:
            reasons.append(f"missing_flag:{flag}")
    if "--task-id-filter" not in cmd or cmd[cmd.index("--task-id-filter") + 1] != ",".join(task_ids):
        reasons.append("task_id_filter_mismatch")
    if "--preflight-only" not in cmd:
        reasons.append("preflight_guard_missing")
    return {
        "passed": not reasons,
        "reason_codes": reasons,
        "task_count": len(task_ids),
        "max_preflight_tasks": MAX_PREFLIGHT_TASKS,
        "same_model": env.get("NEXUS_CODEX_MODEL_NAME") == env.get("NEXUS_DIRECT_CODEX_MODEL"),
        "preflight_only": "--preflight-only" in cmd,
    }


def latest_jsonl(output_dir: Path, prefix: str) -> Path | None:
    candidates = sorted(output_dir.glob(f"{prefix}_*.jsonl"), key=lambda path: path.stat().st_mtime)
    return candidates[-1] if candidates else None


def summarize(output_dir: Path) -> dict[str, Any]:
    with_file = latest_jsonl(output_dir, "with_nexus")
    without_file = latest_jsonl(output_dir, "without_nexus")
    return {
        "with_nexus_file": str(with_file or ""),
        "without_nexus_file": str(without_file or ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a fixed Codex bare vs Codex+Nexus smoke.")
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--output-dir", default=".nexus/reports/bench_codex55_nexus_local_smoke")
    parser.add_argument("--task-id-filter", default=",".join(DEFAULT_TASK_IDS))
    parser.add_argument("--print-only", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)

    task_ids = tuple(item.strip() for item in args.task_id_filter.split(",") if item.strip())
    cmd = build_command(output_dir=args.output_dir, task_ids=task_ids, preflight_only=bool(args.preflight_only))
    plan_validation = validate_smoke_plan(cmd=cmd, env=benchmark_env(str(args.model)), task_ids=task_ids)
    if args.print_only:
        print(
            json.dumps(
                {"command": cmd, "env_model": args.model, "task_ids": list(task_ids), "plan_validation": plan_validation},
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0 if plan_validation["passed"] else 2
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(cmd, cwd=repo_root, env=benchmark_env(str(args.model)), text=True, check=False)
    payload = {
        "returncode": result.returncode,
        "output_dir": str((repo_root / args.output_dir).resolve()),
        "task_ids": list(task_ids),
        "preflight_only": bool(args.preflight_only),
        **summarize((repo_root / args.output_dir).resolve()),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
