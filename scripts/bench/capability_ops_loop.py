#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
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


def _load_jsonl_rows(path: str | Path) -> list[dict[str, Any]]:
    fp = Path(path)
    if not fp.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in fp.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def _median(values: list[float], default: float = 0.0) -> float:
    if not values:
        return float(default)
    return float(statistics.median(values))


def _compute_pillar_scores(with_rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = max(1, len(with_rows))
    lance_hits = sum(1 for r in with_rows if int(r.get("route_findings_hits", 0) or 0) > 0)
    memory_hits = sum(1 for r in with_rows if int(r.get("prior_fix_hits", 0) or 0) > 0)
    mempalace_hits = sum(1 for r in with_rows if not bool(r.get("guard_hit", False)))
    belief_values = [float(r.get("belief_confidence", 0.0) or 0.0) for r in with_rows]
    artifact_hits = sum(
        1
        for r in with_rows
        if str(r.get("semantic_status", "")) in {"VERIFIED", "PARTIAL"} and not bool(r.get("report_trust_mismatch", True))
    )
    scores = {
        "LanceDB": round(lance_hits / total, 4),
        "Memory": round(memory_hits / total, 4),
        "MemPalace": round(mempalace_hits / total, 4),
        "Belief": round(max(0.0, min(1.0, _avg(belief_values))), 4),
        "Artifact": round(artifact_hits / total, 4),
    }
    return {
        "scores": scores,
        "overall": round(_avg(list(scores.values())), 4),
    }


def _compute_self_heal_metrics(with_rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = max(1, len(with_rows))
    success_rows = [r for r in with_rows if str(r.get("status", "")) == "SUCCESS"]
    attempts_gt_one = [r for r in with_rows if int(r.get("attempt_count", 0) or 0) > 1]
    repair_success_count = sum(1 for r in attempts_gt_one if str(r.get("status", "")) == "SUCCESS")
    first_pass_success = sum(
        1 for r in with_rows if int(r.get("attempt_count", 0) or 0) <= 1 and str(r.get("status", "")) == "SUCCESS"
    )
    fallback_activated = sum(
        1 for r in with_rows if bool(r.get("guard_nightshift_recommended", False)) or int(r.get("guard_stage1_fail_signals", 0) or 0) > 0
    )
    attempt_values = [float(r.get("attempt_count", 0) or 0.0) for r in with_rows]
    return {
        "solve_rate": round(len(success_rows) / total, 4),
        "first_pass_success_rate": round(first_pass_success / total, 4),
        "repair_attempt_rate": round(len(attempts_gt_one) / total, 4),
        "repair_success_rate": round((repair_success_count / len(attempts_gt_one)) if attempts_gt_one else 0.0, 4),
        "fallback_activation_rate": round(fallback_activated / total, 4),
        "avg_attempt_count": round(_avg(attempt_values), 4),
    }


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


def _extract_kpi(eval_payload: dict[str, Any]) -> dict[str, float]:
    with_summary = (eval_payload.get("a") or {}).get("summary", {}) if isinstance(eval_payload, dict) else {}
    without_summary = (eval_payload.get("b") or {}).get("summary", {}) if isinstance(eval_payload, dict) else {}
    with_solve = _num(with_summary, "solve_rate")
    with_semantic = _num(with_summary, "semantic_verified_rate")
    with_wall = _num(with_summary, "avg_wall_duration_sec")
    without_wall = _num(without_summary, "avg_wall_duration_sec")
    return {
        "with_solve_rate": with_solve,
        "with_semantic_verified_rate": with_semantic,
        "with_avg_wall_duration_sec": with_wall,
        "without_avg_wall_duration_sec": without_wall,
        "wall_overhead_sec": max(0.0, with_wall - without_wall),
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
        "--tuning-profile",
        profile,
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
    kpi = _extract_kpi(eval_payload)
    with_rows = _load_jsonl_rows(with_file)
    pillar_metrics = _compute_pillar_scores(with_rows)
    self_heal_metrics = _compute_self_heal_metrics(with_rows)

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
            "--tuning-profile",
            profile,
            "--without-mode",
            "bare",
            "--llm-safe-probe",
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
        else:
            cross_cmd = [
                "uv",
                "run",
                "python",
                "scripts/bench/capability_ab_runner.py",
                "--tasks-file",
                "scripts/bench/capability_tasks_cross_module_v1.json",
                "--difficulty",
                "hard",
                "--max-tasks",
                "3",
                "--with-nexus-runner",
                "inprocess",
                "--with-llm-mode",
                "hard",
                "--tuning-profile",
                profile,
                "--without-mode",
                "bare",
                "--llm-safe-probe",
                "--neutralize-history",
                "--output-dir",
                str(output_dir),
            ]
            cross_res = _run(cross_cmd, cwd=repo_root)
            cross_probe_payload: dict[str, Any] = {"status": "FAILED", "reason": "cross_module_probe_failed"}
            if cross_res.returncode == 0:
                cross_raw = _extract_json(cross_res.stdout)
                if cross_raw.get("with_nexus_file") and cross_raw.get("without_nexus_file"):
                    cross_eval_file = output_dir / f"ab_eval_cross_module_probe_{ts}.json"
                    cross_eval_cmd = [
                        "uv",
                        "run",
                        "python",
                        "scripts/bench/ab_eval.py",
                        "--a",
                        str(cross_raw["with_nexus_file"]),
                        "--b",
                        str(cross_raw["without_nexus_file"]),
                        "--output-file",
                        str(cross_eval_file),
                        "--output-json",
                    ]
                    cross_eval_res = _run(cross_eval_cmd, cwd=repo_root)
                    cross_eval = _extract_json(cross_eval_res.stdout) if cross_eval_res.returncode == 0 else {}
                    with_cross_rows = _load_jsonl_rows(str(cross_raw["with_nexus_file"]))
                    cross_probe_payload = {
                        "status": "SUCCESS" if cross_eval_res.returncode == 0 else "FAILED",
                        "paths": {
                            "with_nexus_file": str(cross_raw.get("with_nexus_file", "")),
                            "without_nexus_file": str(cross_raw.get("without_nexus_file", "")),
                            "ab_eval_file": str(cross_eval_file),
                        },
                        "ab_eval": cross_eval,
                        "pillars": _compute_pillar_scores(with_cross_rows),
                        "self_heal": _compute_self_heal_metrics(with_cross_rows),
                    }
            llm_probe_payload["cross_module_refactor_probe"] = cross_probe_payload

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
            f".nexus/config/capability_tuning_{profile}.json",
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
        "kpi": kpi,
        "health": health,
        "pillars": pillar_metrics,
        "self_heal": self_heal_metrics,
        "llm_probe": llm_probe_payload,
        "autotune": autotune_payload or None,
    }
    report_path = output_dir / f"ops_loop_{profile}_{ts}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    report["report_file"] = str(report_path)
    return report


def run_ops_loop_rounds(
    *,
    repo_root: Path,
    profile: str,
    output_dir: Path,
    apply_autotune: bool,
    with_llm_mode: str = "off",
    run_llm_probe: bool = False,
    rounds: int = 3,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    reports: list[dict[str, Any]] = []
    for _ in range(max(1, rounds)):
        reports.append(
            run_ops_loop(
                repo_root=repo_root,
                profile=profile,
                output_dir=output_dir,
                apply_autotune=apply_autotune,
                with_llm_mode=with_llm_mode,
                run_llm_probe=run_llm_probe,
            )
        )
    solve_values = [float((r.get("kpi", {}) or {}).get("with_solve_rate", 0.0) or 0.0) for r in reports]
    semantic_values = [float((r.get("kpi", {}) or {}).get("with_semantic_verified_rate", 0.0) or 0.0) for r in reports]
    wall_values = [float((r.get("kpi", {}) or {}).get("with_avg_wall_duration_sec", 0.0) or 0.0) for r in reports]
    wall_without_values = [float((r.get("kpi", {}) or {}).get("without_avg_wall_duration_sec", 0.0) or 0.0) for r in reports]
    median_kpi = {
        "with_solve_rate": round(_median(solve_values), 4),
        "with_semantic_verified_rate": round(_median(semantic_values), 4),
        "with_avg_wall_duration_sec": round(_median(wall_values), 4),
        "without_avg_wall_duration_sec": round(_median(wall_without_values), 4),
    }
    median_kpi["wall_overhead_sec"] = round(
        max(0.0, median_kpi["with_avg_wall_duration_sec"] - median_kpi["without_avg_wall_duration_sec"]), 4
    )
    trend_gate = {
        "verdict": (
            "PASS"
            if (
                median_kpi["with_solve_rate"] >= 0.95
                and median_kpi["with_semantic_verified_rate"] >= 0.95
                and median_kpi["wall_overhead_sec"] <= 1.5
            )
            else "WARN"
        ),
        "rules": {
            "min_solve_rate": 0.95,
            "min_semantic_rate": 0.95,
            "max_wall_overhead_sec": 1.5,
        },
        "median_kpi": median_kpi,
    }
    final = dict(reports[-1])
    final["rounds"] = len(reports)
    final["kpi_median_3round"] = median_kpi
    final["trend_gate"] = trend_gate
    final["round_reports"] = [str(r.get("report_file", "")) for r in reports]
    ts = int(datetime.now(timezone.utc).timestamp())
    rounds_report_path = output_dir / f"ops_loop_rounds_{profile}_{ts}.json"
    rounds_report_path.write_text(json.dumps(final, indent=2, ensure_ascii=False), encoding="utf-8")
    final["report_file"] = str(rounds_report_path)
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description="Capability operations loop (daily/iter/weekly).")
    parser.add_argument("--profile", choices=["daily", "iter", "weekly"], required=True)
    parser.add_argument("--output-dir", default=".nexus/reports/bench/ops_loop")
    parser.add_argument("--apply-autotune", action="store_true")
    parser.add_argument("--with-llm-mode", choices=["off", "hard", "all"], default="off")
    parser.add_argument("--run-llm-probe", action="store_true")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--output-json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    if int(args.rounds) > 1:
        payload = run_ops_loop_rounds(
            repo_root=repo_root,
            profile=args.profile,
            output_dir=(repo_root / args.output_dir).resolve(),
            apply_autotune=bool(args.apply_autotune),
            with_llm_mode=str(args.with_llm_mode),
            run_llm_probe=bool(args.run_llm_probe),
            rounds=int(args.rounds),
        )
    else:
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
