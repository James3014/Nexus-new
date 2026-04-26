#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


def _extract_json(stdout: str) -> dict[str, Any]:
    text = (stdout or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
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


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _kpi_from_eval(
    eval_payload: dict[str, Any],
    *,
    with_side: str,
    without_side: str,
    overhead_metric: str,
) -> dict[str, Any]:
    with_summary = ((eval_payload.get(with_side) or {}).get("summary") or {})
    without_summary = ((eval_payload.get(without_side) or {}).get("summary") or {})
    kpi = {
        "with_solve_rate": _num(with_summary, "solve_rate"),
        "without_solve_rate": _num(without_summary, "solve_rate"),
        "with_semantic_verified_rate": _num(with_summary, "semantic_verified_rate"),
        "without_semantic_verified_rate": _num(without_summary, "semantic_verified_rate"),
        "with_trust_mismatch_rate": _num(with_summary, "trust_mismatch_rate"),
        "without_trust_mismatch_rate": _num(without_summary, "trust_mismatch_rate"),
        "with_avg_duration_sec": _num(with_summary, "avg_duration_sec"),
        "without_avg_duration_sec": _num(without_summary, "avg_duration_sec"),
        "with_avg_wall_duration_sec": _num(with_summary, "avg_wall_duration_sec"),
        "without_avg_wall_duration_sec": _num(without_summary, "avg_wall_duration_sec"),
        "with_avg_model_calls": _num(with_summary, "avg_model_calls"),
        "without_avg_model_calls": _num(without_summary, "avg_model_calls"),
        "with_avg_total_tokens": _num(with_summary, "avg_total_tokens"),
        "without_avg_total_tokens": _num(without_summary, "avg_total_tokens"),
        "with_token_measured_rate": _num(with_summary, "token_measured_rate"),
        "without_token_measured_rate": _num(without_summary, "token_measured_rate"),
    }
    kpi["delta_solve_rate"] = round(kpi["with_solve_rate"] - kpi["without_solve_rate"], 4)
    kpi["delta_semantic_verified_rate"] = round(
        kpi["with_semantic_verified_rate"] - kpi["without_semantic_verified_rate"], 4
    )
    kpi["delta_trust_mismatch_rate"] = round(
        kpi["without_trust_mismatch_rate"] - kpi["with_trust_mismatch_rate"], 4
    )
    kpi["overhead_metric"] = overhead_metric
    if overhead_metric == "avg_duration_sec":
        kpi["wall_overhead_sec"] = round(
            max(0.0, kpi["with_avg_duration_sec"] - kpi["without_avg_duration_sec"]), 4
        )
    else:
        kpi["wall_overhead_sec"] = round(
            max(0.0, kpi["with_avg_wall_duration_sec"] - kpi["without_avg_wall_duration_sec"]), 4
        )
    return kpi


def _run_bucket(
    *,
    repo_root: Path,
    output_dir: Path,
    name: str,
    tasks_file: str,
    difficulty: str,
    max_tasks: int,
    tuning_profile: str = "",
    force_flow: str = "",
    with_nexus_runner: str = "inprocess",
    with_llm_mode: str = "off",
    with_model_label: str = "",
    without_model_label: str = "",
    without_mode: str = "bare",
    service_force_baseline: bool = False,
) -> dict[str, Any]:
    ts = int(time.time())
    out_dir = output_dir / name
    out_dir.mkdir(parents=True, exist_ok=True)
    runner_mode = "subprocess" if with_nexus_runner == "service" else str(with_nexus_runner)
    run_cmd = [
        "uv",
        "run",
        "python",
        "scripts/bench/capability_ab_runner.py",
        "--tasks-file",
        tasks_file,
        "--difficulty",
        difficulty,
        "--max-tasks",
        str(max_tasks),
        "--with-nexus-runner",
        runner_mode,
        "--with-llm-mode",
        str(with_llm_mode),
        "--without-mode",
        str(without_mode),
        "--neutralize-history",
        "--disable-learning-loop",
        "--output-dir",
        str(out_dir),
    ]
    if with_model_label:
        run_cmd.extend(["--with-model-label", str(with_model_label)])
    if without_model_label:
        run_cmd.extend(["--without-model-label", str(without_model_label)])
    # For service comparison, selected buckets can enforce baseline flow to reduce variance and wall overhead spikes.
    if without_mode == "service" and service_force_baseline:
        run_cmd.extend(["--force-flow", "baseline"])
    if tuning_profile:
        run_cmd.extend(["--tuning-profile", tuning_profile])
    if force_flow:
        run_cmd.extend(["--force-flow", force_flow])
    run_res = _run(run_cmd, cwd=repo_root)
    if run_res.returncode != 0:
        raise RuntimeError(f"{name}_ab_runner_failed: {run_res.stderr.strip()}")
    run_payload = _extract_json(run_res.stdout)
    with_file = run_payload.get("with_nexus_file")
    without_file = run_payload.get("without_nexus_file")
    if not with_file or not without_file:
        raise RuntimeError(f"{name}_missing_jsonl_paths")

    eval_file = out_dir / f"ab_eval_{name}_{ts}.json"
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
        raise RuntimeError(f"{name}_ab_eval_failed: {eval_res.stderr.strip()}")
    eval_payload = _extract_json(eval_res.stdout)

    if without_mode == "service":
        overhead_metric = "avg_duration_sec"
    else:
        overhead_metric = "avg_wall_duration_sec"
    kpi = _kpi_from_eval(eval_payload, with_side="a", without_side="b", overhead_metric=overhead_metric)
    return {
        "name": name,
        "model_profiles": run_payload.get("model_profiles", {}),
        "paths": {
            "with_nexus_file": str(with_file),
            "without_nexus_file": str(without_file),
            "ab_eval_file": str(eval_file),
        },
        "ab_eval": eval_payload,
        "kpi": kpi,
    }


def _run_file_task_bucket(
    *,
    repo_root: Path,
    output_dir: Path,
    name: str,
    tasks_file: str,
    max_tasks: int,
    model: str,
    timeout_sec: int,
    context_mode: str = "lean",
    invocation_mode: str = "inline",
) -> dict[str, Any]:
    out_dir = output_dir / name
    out_dir.mkdir(parents=True, exist_ok=True)
    run_cmd = [
        "uv",
        "run",
        "python",
        "scripts/bench/capability_file_task_runner.py",
        "--tasks-file",
        tasks_file,
        "--difficulty",
        "hard",
        "--max-tasks",
        str(max_tasks),
        "--model",
        str(model),
        "--timeout-sec",
        str(timeout_sec),
        "--context-mode",
        str(context_mode),
        "--invocation-mode",
        str(invocation_mode),
        "--output-dir",
        str(out_dir),
        "--emit-ab",
        "--output-json",
    ]
    run_res = _run(run_cmd, cwd=repo_root)
    if run_res.returncode != 0:
        raise RuntimeError(f"{name}_file_task_runner_failed: {run_res.stderr.strip()}")
    run_payload = _extract_json(run_res.stdout)
    with_file = run_payload.get("with_nexus_file")
    without_file = run_payload.get("without_nexus_file")
    eval_file = run_payload.get("ab_eval_file")
    if not with_file or not without_file or not eval_file:
        raise RuntimeError(f"{name}_missing_file_task_paths")

    eval_payload = _load_json_file(Path(str(eval_file)))
    if not eval_payload:
        raise RuntimeError(f"{name}_missing_file_task_eval")
    kpi = _kpi_from_eval(
        eval_payload,
        with_side="b",
        without_side="a",
        overhead_metric="avg_duration_sec",
    )
    return {
        "name": name,
        "model_profiles": {
            "with_nexus": str(model),
            "without_nexus": "local-baseline",
        },
        "paths": {
            "with_nexus_file": str(with_file),
            "without_nexus_file": str(without_file),
            "ab_eval_file": str(eval_file),
        },
        "ab_eval": eval_payload,
        "kpi": kpi,
    }


def _score_bucket(kpi: dict[str, Any], *, comparison_mode: str) -> float:
    score = (
        0.45 * float(kpi.get("delta_solve_rate", 0.0))
        + 0.40 * float(kpi.get("delta_semantic_verified_rate", 0.0))
        + 0.25 * float(kpi.get("delta_trust_mismatch_rate", 0.0))
    )
    overhead = float(kpi.get("wall_overhead_sec", 0.0))
    if comparison_mode == "service" and overhead > 1.0:
        score -= min(0.2, 0.05 + (overhead - 1.0) * 0.05)
    return round(max(0.0, min(1.0, score)), 4)


def _realism_score_bucket(kpi: dict[str, Any]) -> float:
    trust_ok = 1.0 - min(1.0, float(kpi.get("with_trust_mismatch_rate", 1.0)))
    model_observed = 1.0 if float(kpi.get("with_avg_model_calls", 0.0)) > 0 else 0.0
    token_observed = float(kpi.get("with_token_measured_rate", 0.0))
    observability = max(model_observed, token_observed)
    score = (
        0.30 * float(kpi.get("with_solve_rate", 0.0))
        + 0.35 * float(kpi.get("with_semantic_verified_rate", 0.0))
        + 0.25 * trust_ok
        + 0.10 * observability
    )
    return round(max(0.0, min(1.0, score)), 4)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full A/B report across daily/hard/cross-module buckets.")
    parser.add_argument("--output-dir", default=".nexus/reports/bench/full_ab")
    parser.add_argument("--daily-max-tasks", type=int, default=6)
    parser.add_argument("--hard-max-tasks", type=int, default=6)
    parser.add_argument("--cross-max-tasks", type=int, default=6)
    parser.add_argument("--cross-tasks-file", default="scripts/bench/capability_tasks_cross_module_v1.json")
    parser.add_argument("--enable-stress-cross-bucket", action="store_true")
    parser.add_argument("--stress-max-tasks", type=int, default=6)
    parser.add_argument("--stress-tasks-file", default="scripts/bench/capability_tasks_cross_module_v1.json")
    parser.add_argument("--stress-force-flow", choices=["auto", "baseline", "hyper_sprint"], default="auto")
    parser.add_argument("--stress-tuning-profile", choices=["daily", "iter", "weekly"], default="iter")
    parser.add_argument("--enable-flash-file-task-bucket", action="store_true")
    parser.add_argument(
        "--flash-file-task-tasks-file",
        default="scripts/bench/capability_flash_xmodule_tasks_v1.json",
    )
    parser.add_argument("--flash-file-task-max-tasks", type=int, default=3)
    parser.add_argument("--flash-file-task-model", default="gemini-3-flash-preview")
    parser.add_argument("--flash-file-task-timeout-sec", type=int, default=240)
    parser.add_argument("--flash-file-task-context-mode", choices=["full", "lean", "micro"], default="lean")
    parser.add_argument("--flash-file-task-invocation-mode", choices=["file", "inline", "function"], default="inline")
    parser.add_argument("--with-nexus-runner", choices=["inprocess", "subprocess", "service"], default="inprocess")
    parser.add_argument("--with-llm-mode", choices=["off", "hard", "all"], default="off")
    parser.add_argument("--with-model-label", default="")
    parser.add_argument("--without-model-label", default="")
    parser.add_argument("--without-mode", choices=["service", "bare"], default="bare")
    parser.add_argument("--output-json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    output_dir = (repo_root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    buckets = [
        _run_bucket(
            repo_root=repo_root,
            output_dir=output_dir,
            name="daily",
            tasks_file="scripts/bench/capability_tasks_v1.json",
            difficulty="all",
            max_tasks=max(1, int(args.daily_max_tasks)),
            tuning_profile="daily",
            with_nexus_runner=str(args.with_nexus_runner),
            with_llm_mode=str(args.with_llm_mode),
            with_model_label=str(args.with_model_label),
            without_model_label=str(args.without_model_label),
            without_mode=str(args.without_mode),
            service_force_baseline=True,
        ),
        _run_bucket(
            repo_root=repo_root,
            output_dir=output_dir,
            name="hard",
            tasks_file="scripts/bench/capability_tasks_v1.json",
            difficulty="hard",
            max_tasks=max(1, int(args.hard_max_tasks)),
            tuning_profile="iter",
            with_nexus_runner=str(args.with_nexus_runner),
            with_llm_mode=str(args.with_llm_mode),
            with_model_label=str(args.with_model_label),
            without_model_label=str(args.without_model_label),
            without_mode=str(args.without_mode),
            service_force_baseline=True,
        ),
        _run_bucket(
            repo_root=repo_root,
            output_dir=output_dir,
            name="cross_module",
            tasks_file=str(args.cross_tasks_file),
            difficulty="hard",
            max_tasks=max(1, int(args.cross_max_tasks)),
            tuning_profile="iter",
            with_nexus_runner=str(args.with_nexus_runner),
            with_llm_mode=str(args.with_llm_mode),
            with_model_label=str(args.with_model_label),
            without_model_label=str(args.without_model_label),
            without_mode=str(args.without_mode),
        ),
    ]
    if args.enable_stress_cross_bucket:
        stress_force_flow = "" if str(args.stress_force_flow) == "auto" else str(args.stress_force_flow)
        buckets.append(
            _run_bucket(
                repo_root=repo_root,
                output_dir=output_dir,
                name="cross_module_stress",
                tasks_file=str(args.stress_tasks_file),
                difficulty="hard",
                max_tasks=max(1, int(args.stress_max_tasks)),
                tuning_profile=str(args.stress_tuning_profile),
                force_flow=stress_force_flow,
                with_nexus_runner=str(args.with_nexus_runner),
                with_llm_mode=str(args.with_llm_mode),
                with_model_label=str(args.with_model_label),
                without_model_label=str(args.without_model_label),
                without_mode=str(args.without_mode),
            ),
        )

    if args.enable_flash_file_task_bucket:
        buckets.append(
            _run_file_task_bucket(
                repo_root=repo_root,
                output_dir=output_dir,
                name="flash_file_task_cross_module",
                tasks_file=str(args.flash_file_task_tasks_file),
                max_tasks=max(1, int(args.flash_file_task_max_tasks)),
                model=str(args.flash_file_task_model),
                timeout_sec=max(1, int(args.flash_file_task_timeout_sec)),
                context_mode=str(args.flash_file_task_context_mode),
                invocation_mode=str(args.flash_file_task_invocation_mode),
            ),
        )

    if args.enable_stress_cross_bucket:
        weight = {"daily": 0.25, "hard": 0.3, "cross_module": 0.25, "cross_module_stress": 0.2}
    else:
        weight = {"daily": 0.3, "hard": 0.4, "cross_module": 0.3}
    if args.enable_flash_file_task_bucket and args.enable_stress_cross_bucket:
        weight = {
            "daily": 0.2,
            "hard": 0.25,
            "cross_module": 0.2,
            "cross_module_stress": 0.15,
            "flash_file_task_cross_module": 0.2,
        }
    elif args.enable_flash_file_task_bucket:
        weight = {"daily": 0.22, "hard": 0.28, "cross_module": 0.25, "flash_file_task_cross_module": 0.25}
    bucket_scores = {bucket["name"]: _score_bucket(bucket["kpi"], comparison_mode=str(args.without_mode)) for bucket in buckets}
    realism_bucket_scores = {bucket["name"]: _realism_score_bucket(bucket["kpi"]) for bucket in buckets}
    weighted_score = round(sum(weight[name] * score for name, score in bucket_scores.items()), 4)
    realism_score = round(sum(weight[name] * score for name, score in realism_bucket_scores.items()), 4)
    verdict = "PASS" if weighted_score >= 0.75 else "WARN"
    realism_verdict = "PASS" if realism_score >= 0.9 else "WARN"

    payload = {
        "status": "SUCCESS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "comparison_mode": str(args.without_mode),
        "with_llm_mode": str(args.with_llm_mode),
        "model_profiles": buckets[0].get("model_profiles", {}) if buckets else {},
        "buckets": buckets,
        "bucket_scores": bucket_scores,
        "realism_bucket_scores": realism_bucket_scores,
        "weighted_score": weighted_score,
        "realism_score": realism_score,
        "verdict": verdict,
        "realism_verdict": realism_verdict,
        "weights": weight,
        "targets": {
            "min_delta_solve_rate_hard": 0.6,
            "min_delta_semantic_verified_rate_hard": 0.6,
            "max_wall_overhead_sec_daily": 1.0,
        },
    }
    report_file = output_dir / f"full_ab_report_{int(time.time())}.json"
    report_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    payload["report_file"] = str(report_file)

    if args.output_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Full A/B report done: {report_file}")
        print(f"Weighted score: {weighted_score} ({verdict})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
