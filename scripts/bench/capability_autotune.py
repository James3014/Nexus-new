#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_eval(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compute_tuning(eval_payload: dict[str, Any]) -> dict[str, Any]:
    with_summary = (eval_payload.get("a") or {}).get("summary", {})
    without_summary = (eval_payload.get("b") or {}).get("summary", {})

    def _num(src: dict[str, Any], key: str, default: float) -> float:
        raw = src.get(key, default)
        try:
            return float(raw)
        except Exception:
            return float(default)

    with_solve = _num(with_summary, "solve_rate", 0.0)
    with_trust_mismatch = _num(with_summary, "trust_mismatch_rate", 1.0)
    wall_with = _num(with_summary, "avg_wall_duration_sec", 0.0)
    wall_without = _num(without_summary, "avg_wall_duration_sec", 0.0)
    wall_overhead = max(0.0, wall_with - wall_without)

    knobs = {
        "candidate_boost": 0,
        "max_rounds_boost": 0,
        "stage1_parallel_boost": 0,
        "baseline_fast_sec": 0.0,
        "skip_baseline_probe_for_hard": False,
    }
    reasons: list[str] = []

    if with_trust_mismatch > 0.0:
        reasons.append("trust_mismatch_detected_keep_conservative")
        knobs["baseline_fast_sec"] = 0.0
    else:
        if with_solve < 0.9:
            knobs["candidate_boost"] = 1
            knobs["max_rounds_boost"] = 1
            reasons.append("solve_rate_below_target_expand_search")
        if wall_overhead > 0.8:
            knobs["stage1_parallel_boost"] = -1
            reasons.append("wall_overhead_high_reduce_parallel")
            if with_solve >= 0.95:
                knobs["skip_baseline_probe_for_hard"] = True
                reasons.append("strong_quality_enable_hard_probe_skip")
            else:
                knobs["skip_baseline_probe_for_hard"] = False
                reasons.append("protect_solve_rate_keep_hard_probe")
        elif with_solve >= 0.95 and wall_overhead < 0.5:
            knobs["stage1_parallel_boost"] = 1
            reasons.append("strong_quality_low_overhead_allow_parallel_boost")

    return {
        "status": "SUCCESS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Capability autotune from A/B evaluation report.")
    parser.add_argument("--eval-file", required=True, type=Path)
    parser.add_argument(
        "--tuning-file",
        default=Path(".nexus/config/capability_tuning.json"),
        type=Path,
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output-json", action="store_true")
    args = parser.parse_args()

    eval_payload = _load_eval(args.eval_file)
    tuning = compute_tuning(eval_payload)

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
