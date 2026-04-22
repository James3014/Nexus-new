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


def run_ops_loop(
    *,
    repo_root: Path,
    profile: str,
    output_dir: Path,
    apply_autotune: bool,
    with_llm_mode: str = "off",
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
    parser.add_argument("--output-json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    payload = run_ops_loop(
        repo_root=repo_root,
        profile=args.profile,
        output_dir=(repo_root / args.output_dir).resolve(),
        apply_autotune=bool(args.apply_autotune),
        with_llm_mode=str(args.with_llm_mode),
    )
    if args.output_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"✅ Capability ops loop completed ({payload['profile']})")
        print(f"Report: {payload['report_file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
