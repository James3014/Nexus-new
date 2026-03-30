#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class GateThresholds:
    check_ratio_min: float = 70.0
    proof_ratio_min: float = 95.0
    freeze_ratio_max: float = 20.0
    fail_fast_proof_floor: float = 90.0
    fail_fast_freeze_ceiling: float = 35.0
    min_generated_patches: int = 10
    window_size: int = 20
    required_consecutive_windows: int = 3
    global_gate_pass_rate_min: float = 80.0
    conservative_warmup_rounds: int = 30


@dataclass
class GateMetrics:
    check_ratio: float
    proof_ratio: float
    freeze_ratio: float
    generated_patches: int
    anti_cheat_valid: bool
    passed: bool


def _pct(n: float, d: float) -> float:
    if d <= 0:
        return 0.0
    return round((n / d) * 100.0, 2)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _evaluate_gate(rows: list[dict[str, Any]], t: GateThresholds) -> GateMetrics:
    task_driven_rounds = len(rows)
    checks_triggered = sum(1 for r in rows if bool(r.get("checks_triggered")))
    generated_patches = sum(int(r.get("generated_patches", 0) or 0) for r in rows)
    proof_passed = sum(int(r.get("proof_passed_patches", 0) or 0) for r in rows)
    frozen_rounds = sum(1 for r in rows if bool(r.get("learning_frozen")))

    check_ratio = _pct(checks_triggered, task_driven_rounds)
    proof_ratio = _pct(proof_passed, generated_patches)
    freeze_ratio = _pct(frozen_rounds, task_driven_rounds)

    anti_cheat_valid = generated_patches >= t.min_generated_patches
    passed = (
        anti_cheat_valid
        and check_ratio >= t.check_ratio_min
        and proof_ratio >= t.proof_ratio_min
        and freeze_ratio < t.freeze_ratio_max
    )
    return GateMetrics(
        check_ratio=check_ratio,
        proof_ratio=proof_ratio,
        freeze_ratio=freeze_ratio,
        generated_patches=generated_patches,
        anti_cheat_valid=anti_cheat_valid,
        passed=passed,
    )


def _fail_bucket(row: dict[str, Any], t: GateThresholds) -> str:
    # 🟢 修正：優先保留模擬器傳入的診斷分桶 (RCA 導向)
    if "fail_bucket" in row and row["fail_bucket"] != "none":
        return str(row["fail_bucket"])

    proof_ratio = float(row.get("proof_ratio", 0.0) or 0.0)
    freeze_ratio = float(row.get("freeze_ratio", 0.0) or 0.0)
    
    # 🟢 修正：使用正式門檻而非 fail_fast 門檻進行分類
    proof_fail = proof_ratio < t.proof_ratio_min
    freeze_fail = freeze_ratio > t.freeze_ratio_max
    
    if proof_fail and freeze_fail:
        return "both_fail"
    if proof_fail:
        return "proof_fail"
    if freeze_fail:
        return "freeze_fail"
    return "none"


def analyze(round_summary_path: Path, output_dir: Path, thresholds: GateThresholds) -> dict[str, Any]:
    rows = _read_jsonl(round_summary_path)
    if not rows:
        raise ValueError(f"No rows found in {round_summary_path}")

    evaluated_rows: list[dict[str, Any]] = []
    window_pass_history: list[bool] = []
    max_consecutive = 0
    current_consecutive = 0
    fail_buckets: Counter[str] = Counter()
    fail_reasons: Counter[str] = Counter()

    for idx in range(len(rows)):
        row = dict(rows[idx])
        start = max(0, idx + 1 - thresholds.window_size)
        window_rows = rows[start : idx + 1]
        window_gate = _evaluate_gate(window_rows, thresholds)
        window_pass = window_gate.passed
        window_pass_history.append(window_pass)
        if window_pass:
            current_consecutive += 1
            max_consecutive = max(max_consecutive, current_consecutive)
        else:
            current_consecutive = 0

        row["window_gate_passed"] = window_pass
        # LocalFit is now explicitly "window gate passed"
        row["local_fit"] = window_pass

        bucket = _fail_bucket(row, thresholds)
        row["fail_bucket"] = bucket
        if bucket != "none":
            fail_buckets[bucket] += 1
            fail_reasons[str(row.get("fail_fast_reason", bucket))] += 1

        if idx + 1 <= thresholds.conservative_warmup_rounds:
            row["mode"] = "conservative"
        else:
            row["mode"] = row.get("mode", "explore")
        evaluated_rows.append(row)

    gate_pass_rate = _pct(sum(1 for x in window_pass_history if x), len(window_pass_history))
    global_converged = (
        gate_pass_rate >= thresholds.global_gate_pass_rate_min
        and max_consecutive >= thresholds.required_consecutive_windows
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    out_summary = output_dir / "round_summary.jsonl"
    out_gate = output_dir / "gate_eval.json"
    out_param = output_dir / "param_state.json"

    with out_summary.open("w", encoding="utf-8") as f:
        for row in evaluated_rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")

    gate_payload = {
        "global_converged": global_converged,
        "gate_pass_rate": gate_pass_rate,
        "max_consecutive_windows": max_consecutive,
        "required_consecutive_windows": thresholds.required_consecutive_windows,
        "window_size": thresholds.window_size,
        "thresholds": asdict(thresholds),
        "fail_bucket_counts": dict(fail_buckets),
        "top_fail_reasons": [{"reason": k, "count": v} for k, v in fail_reasons.most_common(3)],
    }
    out_gate.write_text(json.dumps(gate_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    last = evaluated_rows[-1]
    param_payload = {
        "mode": last.get("mode"),
        "round": last.get("round", len(evaluated_rows)),
        "local_fit": bool(last.get("local_fit", False)),
        "global_converged": global_converged,
        "alignment": float(last.get("alignment", 0.0) or 0.0),
        "gate_pass_rate": gate_pass_rate,
        "params": last.get("params", {}),
    }
    out_param.write_text(json.dumps(param_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "rows": len(evaluated_rows),
        "global_converged": global_converged,
        "gate_pass_rate": gate_pass_rate,
        "max_consecutive_windows": max_consecutive,
        "output_dir": str(output_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Harden Nexus formal research gate evaluation")
    parser.add_argument("--round-summary", required=True, help="Input round_summary.jsonl path")
    parser.add_argument("--output-dir", required=True, help="Output dir for gate_eval/param_state/round_summary")
    parser.add_argument("--window-size", type=int, default=20)
    parser.add_argument("--required-consecutive", type=int, default=3)
    parser.add_argument("--global-pass-rate-min", type=float, default=80.0)
    parser.add_argument("--proof-ratio-min", type=float, default=95.0)
    parser.add_argument("--check-ratio-min", type=float, default=70.0)
    parser.add_argument("--freeze-ratio-max", type=float, default=20.0)
    args = parser.parse_args()

    thresholds = GateThresholds(
        window_size=args.window_size,
        required_consecutive_windows=args.required_consecutive,
        global_gate_pass_rate_min=args.global_pass_rate_min,
        proof_ratio_min=args.proof_ratio_min,
        check_ratio_min=args.check_ratio_min,
        freeze_ratio_max=args.freeze_ratio_max,
    )
    result = analyze(Path(args.round_summary), Path(args.output_dir), thresholds)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
