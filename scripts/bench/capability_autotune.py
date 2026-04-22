#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_eval(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _median(values: list[float], default: float) -> float:
    if not values:
        return float(default)
    return float(statistics.median(values))


def _collect_median_inputs(eval_payload: dict[str, Any], history_payloads: list[dict[str, Any]] | None) -> dict[str, float]:
    payloads = [eval_payload]
    if history_payloads:
        payloads.extend(history_payloads)

    with_solve_values: list[float] = []
    with_trust_values: list[float] = []
    wall_with_values: list[float] = []
    wall_without_values: list[float] = []
    for payload in payloads:
        with_summary = (payload.get("a") or {}).get("summary", {})
        without_summary = (payload.get("b") or {}).get("summary", {})
        try:
            with_solve_values.append(float(with_summary.get("solve_rate", 0.0)))
            with_trust_values.append(float(with_summary.get("trust_mismatch_rate", 1.0)))
            wall_with_values.append(float(with_summary.get("avg_wall_duration_sec", 0.0)))
            wall_without_values.append(float(without_summary.get("avg_wall_duration_sec", 0.0)))
        except Exception:
            continue
    with_solve = _median(with_solve_values, 0.0)
    with_trust_mismatch = _median(with_trust_values, 1.0)
    wall_with = _median(wall_with_values, 0.0)
    wall_without = _median(wall_without_values, 0.0)
    return {
        "with_solve_rate": with_solve,
        "with_trust_mismatch_rate": with_trust_mismatch,
        "with_avg_wall_duration_sec": wall_with,
        "without_avg_wall_duration_sec": wall_without,
        "wall_overhead_sec": max(0.0, wall_with - wall_without),
        "sample_count": max(1, len(with_solve_values)),
    }


def _read_previous_knobs(previous_tuning: dict[str, Any] | None) -> dict[str, Any]:
    raw = (previous_tuning or {}).get("knobs", {})
    if not isinstance(raw, dict):
        return {}
    return raw


def compute_tuning(
    eval_payload: dict[str, Any],
    *,
    history_payloads: list[dict[str, Any]] | None = None,
    previous_tuning: dict[str, Any] | None = None,
) -> dict[str, Any]:
    med = _collect_median_inputs(eval_payload, history_payloads)
    with_solve = med["with_solve_rate"]
    with_trust_mismatch = med["with_trust_mismatch_rate"]
    wall_with = med["with_avg_wall_duration_sec"]
    wall_without = med["without_avg_wall_duration_sec"]
    wall_overhead = med["wall_overhead_sec"]
    sample_count = int(med["sample_count"])
    prev_knobs = _read_previous_knobs(previous_tuning)

    knobs = {
        "candidate_boost": int(prev_knobs.get("candidate_boost", 0) or 0),
        "max_rounds_boost": int(prev_knobs.get("max_rounds_boost", 0) or 0),
        "stage1_parallel_boost": int(prev_knobs.get("stage1_parallel_boost", 0) or 0),
        "baseline_fast_sec": 0.0,
        "skip_baseline_probe_for_hard": bool(prev_knobs.get("skip_baseline_probe_for_hard", False)),
    }
    reasons: list[str] = []

    if with_trust_mismatch > 0.0:
        reasons.append("trust_mismatch_detected_keep_conservative")
        knobs["candidate_boost"] = 0
        knobs["max_rounds_boost"] = 0
        knobs["stage1_parallel_boost"] = min(0, int(knobs.get("stage1_parallel_boost", 0) or 0))
        knobs["baseline_fast_sec"] = 0.0
        knobs["skip_baseline_probe_for_hard"] = False
    else:
        # Solve-rate hysteresis:
        # below 0.92 => expand search; above 0.97 => release expansion; otherwise hold.
        if with_solve < 0.92:
            knobs["candidate_boost"] = 1
            knobs["max_rounds_boost"] = 1
            reasons.append("solve_rate_below_target_expand_search")
        elif with_solve > 0.97:
            knobs["candidate_boost"] = 0
            knobs["max_rounds_boost"] = 0
            reasons.append("solve_rate_strong_release_expand_search")
        else:
            reasons.append("solve_rate_hysteresis_hold_previous")

        # Wall-overhead hysteresis:
        # above 0.80 => reduce parallel; below 0.55 and strong quality => allow boost; otherwise hold.
        if wall_overhead > 0.8:
            knobs["stage1_parallel_boost"] = -1
            reasons.append("wall_overhead_high_reduce_parallel")
            if with_solve >= 0.95:
                knobs["skip_baseline_probe_for_hard"] = True
                reasons.append("strong_quality_enable_hard_probe_skip")
            else:
                knobs["skip_baseline_probe_for_hard"] = False
                reasons.append("protect_solve_rate_keep_hard_probe")
        elif with_solve >= 0.95 and wall_overhead < 0.55:
            knobs["stage1_parallel_boost"] = 1
            reasons.append("strong_quality_low_overhead_allow_parallel_boost")
            knobs["skip_baseline_probe_for_hard"] = False
        else:
            reasons.append("wall_overhead_hysteresis_hold_previous")

    return {
        "status": "SUCCESS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "aggregation_mode": "median",
        "aggregation_window": sample_count,
        "input_metrics": {
            "with_solve_rate": with_solve,
            "with_trust_mismatch_rate": with_trust_mismatch,
            "with_avg_wall_duration_sec": wall_with,
            "without_avg_wall_duration_sec": wall_without,
            "wall_overhead_sec": wall_overhead,
        },
        "knobs": knobs,
        "reasons": reasons or ["no_change"],
    }


def _load_recent_eval_payloads(history_dir: Path, *, limit: int, exclude_file: Path | None = None) -> list[dict[str, Any]]:
    if limit <= 0 or not history_dir.exists():
        return []
    files = sorted(history_dir.glob("ab_eval_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    payloads: list[dict[str, Any]] = []
    excluded = exclude_file.resolve() if exclude_file else None
    for fp in files:
        if excluded and fp.resolve() == excluded:
            continue
        try:
            payloads.append(_load_eval(fp))
        except Exception:
            continue
        if len(payloads) >= limit:
            break
    return payloads


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Capability autotune from A/B evaluation report.")
    parser.add_argument("--eval-file", required=True, type=Path)
    parser.add_argument("--history-dir", default=Path(".nexus/reports/bench/ops_loop"), type=Path)
    parser.add_argument("--median-window", type=int, default=3)
    parser.add_argument(
        "--tuning-file",
        default=Path(".nexus/config/capability_tuning.json"),
        type=Path,
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output-json", action="store_true")
    args = parser.parse_args()

    eval_payload = _load_eval(args.eval_file)
    history_payloads = _load_recent_eval_payloads(
        args.history_dir.resolve(),
        limit=max(0, int(args.median_window) - 1),
        exclude_file=args.eval_file.resolve(),
    )
    previous_tuning = {}
    if args.tuning_file.exists():
        try:
            previous_tuning = json.loads(args.tuning_file.read_text(encoding="utf-8"))
        except Exception:
            previous_tuning = {}
    tuning = compute_tuning(
        eval_payload,
        history_payloads=history_payloads,
        previous_tuning=previous_tuning,
    )

    tuning_file = args.tuning_file.resolve()
    backup_file = tuning_file.with_suffix(".prev.json")
    if args.apply:
        if tuning_file.exists():
            _write_json(backup_file, json.loads(tuning_file.read_text(encoding="utf-8")))
        _write_json(tuning_file, tuning)

    if args.output_json:
        print(json.dumps(tuning, indent=2, ensure_ascii=False))
    else:
        print("✅ Capability autotune ready")
        print(f"reasons={','.join(tuning['reasons'])}")
        print(f"apply={args.apply}")
        print(f"tuning_file={tuning_file}")
        if args.apply and backup_file.exists():
            print(f"backup_file={backup_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
