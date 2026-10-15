#!/usr/bin/env python3
"""Build (and optionally run) the counted online A/B command for one lane (wiring plan PR-3).

usage: run_lane.py --lane {strict,treatment} --run-id ID [--repeat N] [--tasks FILE]
                   [--max-tasks N] [--per-call-timeout-sec S] [--output-root DIR]
                   [--treatment-max-model-calls N] [--execute] [-- extra runner args]

Both lanes share every fairness flag of the strict lane (same model on agy for both arms, hidden
verifier only, no hidden feedback, no task hints, ABBA, one per-call cap). The only difference is
``--lane treatment``, which the runner turns into the treatment env for the with-Nexus arm. Without
``--execute`` the command and env are printed (nothing runs, no model call).

Host setup (agy shim, account lease, quota refresh, runtime checkout) stays with the operator's
wrapper script; this helper only fixes the runner flags so the two lanes cannot drift apart.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = "scripts/bench/capability_ab_runner.py"
DEFAULT_TASKS = "scripts/bench/public_benchmark_nexus_value_v1.json"
# Shared by both lanes (2026-10-14 symmetry batch, SYMMETRY_INVENTORY.md S1-S24).
COMMON_FLAGS = (
    "--difficulty",
    "all",
    "--repo-kind-filter",
    "all",
    "--with-nexus-runner",
    "subprocess",
    "--with-llm-mode",
    "all",
    "--without-mode",
    "agy",
    "--require-same-model-baseline",
    "--strict-llm-baseline",
    "--counted-first-attempt",
    "--no-hidden-feedback",
    "--no-nexus-task-hints",
    "--disable-promoted-route-cost-policy",
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
)
COMMON_ENV = {
    "NEXUS_VALUE_HIDDEN_VERIFIER": "1",
    "NEXUS_GATEWAY_PROMPT_TRANSPORT": "stdin",
    "NEXUS_GATEWAY_COMPACT_PROMPT": "1",
    "NEXUS_BENCH_DISABLE_HIDDEN_RETRY": "1",
    "NEXUS_BENCH_DISABLE_DETERMINISTIC_RESCUE": "1",
}


def build_command(
    *,
    lane: str,
    run_id: str,
    repeat: int = 1,
    tasks: str = DEFAULT_TASKS,
    max_tasks: int = 12,
    per_call_timeout_sec: int = 300,
    output_root: str = "artifacts/runtime/online_ab_v1",
    treatment_max_model_calls: int | None = None,
    python: str = sys.executable,
    extra: list[str] | None = None,
) -> tuple[list[str], dict[str, str]]:
    """The runner argv and env updates for one lane; identical except for the lane flags."""

    if lane not in {"strict", "treatment"}:
        raise ValueError(f"unknown lane {lane!r}")
    argv = [
        python,
        RUNNER,
        "--tasks-file",
        tasks,
        "--output-dir",
        f"{output_root}/{run_id}",
        "--max-tasks",
        str(max_tasks),
        "--repeat-trials",
        str(repeat),
        "--timeout-sec",
        "420",
        "--total-timeout-sec",
        "14400",
        "--stop-loss-sec",
        "14400",
        "--per-task-stop-loss-sec",
        "600",
        "--force-flow",
        "hyper_sprint",
        "--per-call-timeout-sec",
        str(per_call_timeout_sec),
        *COMMON_FLAGS,
        "--lane",
        lane,
    ]
    if lane == "treatment" and treatment_max_model_calls is not None:
        argv += ["--treatment-max-model-calls", str(treatment_max_model_calls)]
    argv += list(extra or [])
    env = dict(COMMON_ENV)
    env["NEXUS_BENCH_GATEWAY_TIMEOUT_SEC"] = str(per_call_timeout_sec)
    if lane == "strict":
        # S9: the strict lane is first attempt only (the runner forces this too).
        env["NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL"] = "0"
    return argv, env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    parser.add_argument("--lane", choices=["strict", "treatment"], default="strict")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--tasks", default=os.environ.get("TASKS") or DEFAULT_TASKS)
    parser.add_argument("--max-tasks", type=int, default=int(os.environ.get("MAX_TASKS") or 12))
    parser.add_argument("--per-call-timeout-sec", type=int, default=300)
    parser.add_argument("--output-root", default="artifacts/runtime/online_ab_v1")
    parser.add_argument("--treatment-max-model-calls", type=int, default=None)
    parser.add_argument(
        "--execute", action="store_true", help="run the runner (default: print only)"
    )
    parser.add_argument("extra", nargs=argparse.REMAINDER, help="extra runner args after --")
    args = parser.parse_args(argv)
    extra = [item for item in args.extra if item != "--"]
    command, env = build_command(
        lane=args.lane,
        run_id=args.run_id,
        repeat=args.repeat,
        tasks=args.tasks,
        max_tasks=args.max_tasks,
        per_call_timeout_sec=args.per_call_timeout_sec,
        output_root=args.output_root,
        treatment_max_model_calls=args.treatment_max_model_calls,
        extra=extra,
    )
    if not args.execute:
        print(json.dumps({"env": env, "argv": command, "shell": shlex.join(command)}, indent=2))
        return 0
    return subprocess.run(command, cwd=REPO_ROOT, env={**os.environ, **env}, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
