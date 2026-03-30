#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class ParamKey:
    min_samples: int
    baseline: float
    learning_rate: float


def _run(cmd: list[str], cwd: Path) -> int:
    return subprocess.call(cmd, cwd=str(cwd))


def _sweep_once(
    project_root: Path,
    workspace: Path,
    prefix: str,
    rounds: int,
    proof_ratio_min: float,
    degrade_threshold: float,
    max_step: float,
    degrade_consecutive_rounds: int,
) -> dict:
    configs = [
        {"min_samples": 3, "baseline": 0.50, "learning_rate": 0.40},
        {"min_samples": 3, "baseline": 0.55, "learning_rate": 0.60},
        {"min_samples": 3, "baseline": 0.60, "learning_rate": 0.40},
        {"min_samples": 5, "baseline": 0.55, "learning_rate": 0.40},
        {"min_samples": 5, "baseline": 0.60, "learning_rate": 0.50},
        {"min_samples": 8, "baseline": 0.60, "learning_rate": 0.30},
    ]
    weights = project_root / "scripts" / "core" / "autonomic_weights.json"
    backup = weights.read_text(encoding="utf-8")
    results = []

    try:
        for idx, cfg in enumerate(configs, start=1):
            weights.write_text(backup, encoding="utf-8")
            phase7_cmd = [
                sys.executable,
                str(project_root / "scripts" / "engine" / "nexus_cli.py"),
                "nexus:phase7",
                "--workspace",
                str(workspace),
                "--rounds",
                str(rounds),
                "--proof-ratio-min",
                str(proof_ratio_min),
                "--output-prefix",
                f"{prefix}_sweep_{idx}",
                "--skip-autopilot",
                "--min-samples",
                str(cfg["min_samples"]),
                "--baseline",
                str(cfg["baseline"]),
                "--learning-rate",
                str(cfg["learning_rate"]),
                "--degrade-threshold",
                str(degrade_threshold),
                "--max-step",
                str(max_step),
                "--degrade-consecutive-rounds",
                str(degrade_consecutive_rounds),
            ]
            rc = _run(phase7_cmd, project_root)
            rpt = json.loads(
                (project_root / ".nexus" / "metrics" / "skills_autotune_report.json").read_text(encoding="utf-8")
            )
            suggestions = rpt.get("suggestions", {})
            max_abs_delta = 0.0
            for value in suggestions.values():
                max_abs_delta = max(max_abs_delta, abs(float(value.get("delta", 0.0))))
            results.append(
                {
                    **cfg,
                    "rc": rc,
                    "tuned_skill_count": int(rpt.get("tuned_skill_count", 0)),
                    "max_abs_delta": round(max_abs_delta, 4),
                    "prefix": f"{prefix}_sweep_{idx}",
                }
            )
    finally:
        weights.write_text(backup, encoding="utf-8")

    best = sorted(
        results,
        key=lambda row: (
            row["rc"] != 0,
            -row["tuned_skill_count"],
            -row["max_abs_delta"],
            row["baseline"],
        ),
    )[0]
    report = {"results": results, "best": best}
    report_path = project_root / ".nexus" / "metrics" / f"{prefix}_param_sweep_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"report": str(report_path), **best}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run phase7 sweep/apply loop until best params stabilize.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--proof-ratio-min", type=float, default=95.0)
    parser.add_argument("--max-loops", type=int, default=10)
    parser.add_argument("--stable-wins", type=int, default=3)
    parser.add_argument("--output-prefix", default="phase7_loop")
    parser.add_argument("--degrade-threshold", type=float, default=0.2)
    parser.add_argument("--max-step", type=float, default=0.35)
    parser.add_argument("--degrade-consecutive-rounds", type=int, default=3)
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    workspace = Path(args.workspace).expanduser().resolve()

    best_history: list[ParamKey] = []
    loop_rows: list[dict] = []

    for idx in range(1, args.max_loops + 1):
        loop_prefix = f"{args.output_prefix}_{idx}"
        sweep = _sweep_once(
            project_root=project_root,
            workspace=workspace,
            prefix=loop_prefix,
            rounds=args.rounds,
            proof_ratio_min=args.proof_ratio_min,
            degrade_threshold=args.degrade_threshold,
            max_step=args.max_step,
            degrade_consecutive_rounds=args.degrade_consecutive_rounds,
        )

        key = ParamKey(
            min_samples=int(sweep["min_samples"]),
            baseline=float(sweep["baseline"]),
            learning_rate=float(sweep["learning_rate"]),
        )
        best_history.append(key)

        apply_cmd = [
            sys.executable,
            str(project_root / "scripts" / "engine" / "nexus_cli.py"),
            "nexus:phase7",
            "--workspace",
            str(workspace),
            "--rounds",
            str(args.rounds),
            "--proof-ratio-min",
            str(args.proof_ratio_min),
            "--output-prefix",
            f"{loop_prefix}_best",
            "--skip-autopilot",
            "--autotune-apply",
            "--min-samples",
            str(key.min_samples),
            "--baseline",
            str(key.baseline),
            "--learning-rate",
            str(key.learning_rate),
            "--degrade-threshold",
            str(args.degrade_threshold),
            "--max-step",
            str(args.max_step),
            "--degrade-consecutive-rounds",
            str(args.degrade_consecutive_rounds),
        ]
        apply_rc = _run(apply_cmd, project_root)

        loop_rows.append(
            {
                "loop": idx,
                "best": {
                    "min_samples": key.min_samples,
                    "baseline": key.baseline,
                    "learning_rate": key.learning_rate,
                },
                "apply_rc": apply_rc,
                "sweep_report": sweep["report"],
            }
        )

        if len(best_history) >= args.stable_wins:
            tail = best_history[-args.stable_wins :]
            if all(x == tail[0] for x in tail):
                break

    final = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "workspace": str(workspace),
        "max_loops": args.max_loops,
        "stable_wins": args.stable_wins,
        "loops_executed": len(loop_rows),
        "history": loop_rows,
        "converged": len(best_history) >= args.stable_wins
        and all(x == best_history[-1] for x in best_history[-args.stable_wins :]),
        "final_best": (
            {
                "min_samples": best_history[-1].min_samples,
                "baseline": best_history[-1].baseline,
                "learning_rate": best_history[-1].learning_rate,
            }
            if best_history
            else None
        ),
    }

    out = workspace / f"{args.output_prefix}_final_report_cn.json"
    out.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[phase7-loop] report:", out)
    print("[phase7-loop] converged:", str(final["converged"]).lower())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
