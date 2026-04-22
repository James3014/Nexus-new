#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROFILE_TO_TASKS = {
    "daily": 6,
    "iter": 12,
    "weekly": 30,
}


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


def _extract_json(stdout: str) -> dict[str, Any]:
    text = (stdout or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        pass
    brace_positions = [idx for idx, ch in enumerate(text) if ch == "{"]
    for idx in reversed(brace_positions):
        try:
            payload = json.loads(text[idx:])
            if isinstance(payload, dict):
                return payload
        except Exception:
            continue
    return {}


def _num(src: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(src.get(key, default))
    except Exception:
        return float(default)


def _compute_health_score(eval_payload: dict[str, Any]) -> dict[str, Any]:
    with_summary = (eval_payload.get("a") or {}).get("summary", {}
    ) if isinstance(eval_payload, dict) else {}
    without_summary = (eval_payload.get("b") or {}).get("summary", {}
    ) if isinstance(eval_payload, dict) else {}
    with_solve = _num(with_summary, "solve_rate")
    with_semantic = _num(with_summary, "semantic_verified_rate")
    with_trust = _num(with_summary, "trust_mismatch_rate", 1.0)
    with_wall = _num(with_summary, "avg_wall_duration_sec")
    without_wall = _num(without_summary, "avg_wall_duration_sec")
    wall_overhead = max(0.0, with_wall - without_wall)
    # Weighted score in [0,1], trust mismatch is hard penalty.
    score = (
        0.40 * with_solve
        + 0.35 * with_semantic
        + 0.25 * max(0.0, 1.0 - with_trust)
    )
    if wall_overhead > 1.0:
        score -= min(0.15, 0.05 + (wall_overhead - 1.0) * 0.03)
    score = max(0.0, min(1.0, score))
    verdict = "PASS" if (with_solve >= 0.95 and with_semantic >= 0.95 and with_trust == 0.0) else "WARN"
    return {
        "score": round(score, 4),
        "verdict": verdict,
        "inputs": {
            "with_solve_rate": with_solve,
            "with_semantic_verified_rate": with_semantic,
            "with_trust_mismatch_rate": with_trust,
            "with_avg_wall_duration_sec": with_wall,
            "without_avg_wall_duration_sec": without_wall,
            "wall_overhead_sec": round(wall_overhead, 4),
        },
    }


def run_ops_loop(
    *,
    repo_root: Path,
    profile: str,
    output_dir: Path,
    apply_autotune: bool,
    with_llm_mode: str = "off",
    run_llm_probe: bool = False,
) -> dict[str, Any]:
    max_tasks = PROFILE_TO_TASKS[profile]
    output_dir.mkdir(parents=True, exist_ok=True)

    ab_runner_cmd = [
        "uv",
        "run",
        "python",
        "scripts/bench/capability_ab_runner.py",
        "--tasks-file",
        "scripts/bench/capability_tasks_v1.json",
        "--difficulty",
        "all",
        "--max-tasks",
        str(max_tasks),
        "--with-nexus-runner",
        "inprocess",
        "--with-llm-mode",
        with_llm_mode,
        "--without-mode",
        "bare",
        "--neutralize-history",
        "--output-dir",
        str(output_dir),
    ]
    ab_runner_res = _run(ab_runner_cmd, cwd=repo_root)
    if ab_runner_res.returncode != 0:
        raise RuntimeError(f"ab_runner_failed: {ab_runner_res.stderr.strip()}")
    ab_payload = _extract_json(ab_runner_res.stdout)
    with_file = ab_payload.get("with_nexus_file")
    without_file = ab_payload.get("without_nexus_file")
    if not with_file or not without_file:
        raise RuntimeError("ab_runner_output_missing_files")

    ts = int(datetime.now(timezone.utc).timestamp())
    eval_file = output_dir / f"ab_eval_{ts}.json"
    eval_cmd = [
        "uv",
        "run",
        "python",
        "scripts/bench/ab_eval.py",
        "--a",
        str(with_file),
        "--b",
        str(without_file),
        "--output-file",
        str(eval_file),
        "--output-json",
    ]
    eval_res = _run(eval_cmd, cwd=repo_root)
    if eval_res.returncode != 0:
        raise RuntimeError(f"ab_eval_failed: {eval_res.stderr.strip()}")
    eval_payload = _extract_json(eval_res.stdout)
    health = _compute_health_score(eval_payload)

    llm_probe_payload: dict[str, Any] | None = None
    if run_llm_probe:
        llm_cmd = [
            "uv",
            "run",
            "python",
            "scripts/bench/capability_ab_runner.py",
            "--tasks-file",
            "scripts/bench/capability_tasks_v1.json",
            "--difficulty",
            "hard",
            "--max-tasks",
            "3",
            "--with-nexus-runner",
            "inprocess",
            "--with-llm-mode",
            "hard",
            "--without-mode",
            "bare",
            "--force-flow",
            "hyper_sprint",
            "--neutralize-history",
            "--output-dir",
            str(output_dir),
        ]
        llm_res = _run(llm_cmd, cwd=repo_root)
        if llm_res.returncode == 0:
            llm_raw = _extract_json(llm_res.stdout)
            if llm_raw.get("with_nexus_file") and llm_raw.get("without_nexus_file"):
                llm_eval_file = output_dir / f"ab_eval_llm_probe_{ts}.json"
                llm_eval_cmd = [
                    "uv",
                    "run",
                    "python",
                    "scripts/bench/ab_eval.py",
                    "--a",
                    str(llm_raw["with_nexus_file"]),
                    "--b",
                    str(llm_raw["without_nexus_file"]),
                    "--output-file",
                    str(llm_eval_file),
                    "--output-json",
                ]
                llm_eval_res = _run(llm_eval_cmd, cwd=repo_root)
                llm_eval = _extract_json(llm_eval_res.stdout) if llm_eval_res.returncode == 0 else {}
                llm_probe_payload = {
                    "status": "SUCCESS" if llm_eval_res.returncode == 0 else "FAILED",
                    "paths": {
                        "with_nexus_file": str(llm_raw.get("with_nexus_file", "")),
                        "without_nexus_file": str(llm_raw.get("without_nexus_file", "")),
                        "ab_eval_file": str(llm_eval_file),
                    },
                    "ab_eval": llm_eval,
                }
        if llm_probe_payload is None:
            llm_probe_payload = {
                "status": "FAILED",
                "reason": "llm_probe_run_failed_or_output_missing",
            }

    autotune_payload: dict[str, Any] = {}
    if apply_autotune:
        tune_cmd = [
            "uv",
            "run",
            "python",
            "scripts/bench/capability_autotune.py",
            "--eval-file",
            str(eval_file),
            "--history-dir",
            str(output_dir),
            "--tuning-file",
            ".nexus/config/capability_tuning.json",
            "--apply",
            "--output-json",
        ]
        tune_res = _run(tune_cmd, cwd=repo_root)
        if tune_res.returncode != 0:
            raise RuntimeError(f"autotune_failed: {tune_res.stderr.strip()}")
        autotune_payload = _extract_json(tune_res.stdout)

    report = {
        "status": "SUCCESS",
        "profile": profile,
        "max_tasks": max_tasks,
        "with_llm_mode": with_llm_mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "paths": {
            "with_nexus_file": str(with_file),
            "without_nexus_file": str(without_file),
            "ab_eval_file": str(eval_file),
        },
        "ab_eval": eval_payload,
        "health": health,
        "llm_probe": llm_probe_payload,
        "autotune": autotune_payload or None,
    }
    report_path = output_dir / f"ops_loop_{profile}_{ts}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    report["report_file"] = str(report_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Capability operations loop (daily/iter/weekly).")
    parser.add_argument("--profile", choices=["daily", "iter", "weekly"], required=True)
    parser.add_argument("--output-dir", default=".nexus/reports/bench/ops_loop")
    parser.add_argument("--apply-autotune", action="store_true")
    parser.add_argument("--with-llm-mode", choices=["off", "hard", "all"], default="off")
    parser.add_argument("--run-llm-probe", action="store_true")
    parser.add_argument("--output-json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    payload = run_ops_loop(
        repo_root=repo_root,
        profile=args.profile,
        output_dir=(repo_root / args.output_dir).resolve(),
        apply_autotune=bool(args.apply_autotune),
        with_llm_mode=str(args.with_llm_mode),
        run_llm_probe=bool(args.run_llm_probe),
    )
    if args.output_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"✅ Capability ops loop completed ({payload['profile']})")
        print(f"Report: {payload['report_file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
