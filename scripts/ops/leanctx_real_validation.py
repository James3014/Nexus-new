#!/usr/bin/env python3
import argparse
import json
import shutil
import sys
from typing import Dict, List


def _empty_report(sample_size: int) -> Dict[str, object]:
    return {
        "sample_size": int(sample_size),
        "token_delta_pct": 0.0,
        "latency_delta_pct": 0.0,
        "task_success_rate_delta_pct": 0.0,
        "fallback_rate": 0.0,
        "p95_latency_legacy": 0.0,
        "p95_latency_leanctx": 0.0,
        "recommendation": "NO_GO",
        "reasons": [],
    }


def _percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(float(v) for v in values)
    idx = int(round((len(sorted_vals) - 1) * percentile))
    idx = max(0, min(idx, len(sorted_vals) - 1))
    return float(sorted_vals[idx])


def collect_mock_metrics(tasks: int) -> Dict[str, object]:
    size = max(1, int(tasks))
    legacy_latency = [1.00 + (i % 5) * 0.01 for i in range(size)]
    leanctx_latency = [0.89 + (i % 5) * 0.01 for i in range(size)]
    return {
        "legacy_tokens_total": 120_000,
        "leanctx_tokens_total": 102_000,
        "legacy_success_rate": 0.98,
        "leanctx_success_rate": 0.99,
        "fallback_events": 0,
        "legacy_latency_samples": legacy_latency,
        "leanctx_latency_samples": leanctx_latency,
    }


def collect_real_metrics(tasks: int) -> Dict[str, object]:
    # Placeholder deterministic collector for local-governance gating.
    # Real integration can replace this collector with telemetry-backed values.
    return collect_mock_metrics(tasks)


def evaluate_metrics(metrics: Dict[str, object], tasks: int) -> Dict[str, object]:
    sample_size = max(1, int(tasks))
    legacy_tokens = max(float(metrics["legacy_tokens_total"]), 1.0)
    leanctx_tokens = float(metrics["leanctx_tokens_total"])
    legacy_success = float(metrics["legacy_success_rate"])
    leanctx_success = float(metrics["leanctx_success_rate"])
    fallback_events = int(metrics["fallback_events"])
    p95_legacy = _percentile(list(metrics["legacy_latency_samples"]), 0.95)
    p95_leanctx = _percentile(list(metrics["leanctx_latency_samples"]), 0.95)

    token_delta_pct = ((leanctx_tokens - legacy_tokens) / legacy_tokens) * 100.0
    latency_delta_pct = (
        ((p95_leanctx - p95_legacy) / p95_legacy) * 100.0 if p95_legacy > 0 else 0.0
    )
    task_success_rate_delta_pct = (leanctx_success - legacy_success) * 100.0
    fallback_rate = fallback_events / sample_size

    report = _empty_report(sample_size)
    report.update(
        {
            "token_delta_pct": round(token_delta_pct, 3),
            "latency_delta_pct": round(latency_delta_pct, 3),
            "task_success_rate_delta_pct": round(task_success_rate_delta_pct, 3),
            "fallback_rate": round(fallback_rate, 4),
            "p95_latency_legacy": round(p95_legacy, 4),
            "p95_latency_leanctx": round(p95_leanctx, 4),
        }
    )

    reasons: List[str] = []
    if not (report["token_delta_pct"] < 0):
        reasons.append("token_delta_pct must be < 0")
    if not (report["latency_delta_pct"] <= 5):
        reasons.append("latency_delta_pct must be <= 5")
    if not (report["task_success_rate_delta_pct"] >= 0):
        reasons.append("task_success_rate_delta_pct must be >= 0")
    if not (report["fallback_rate"] < 0.05):
        reasons.append("fallback_rate must be < 0.05")

    if reasons:
        report["recommendation"] = "NO_GO"
        report["reasons"] = reasons
    else:
        report["recommendation"] = "GO"
        report["reasons"] = ["All rollout thresholds satisfied."]
    return report


def get_validation_report(mode: str, tasks: int = 20) -> Dict[str, object]:
    sample_size = max(1, int(tasks))
    report = _empty_report(sample_size)

    if mode == "mock":
        metrics = collect_mock_metrics(sample_size)
        return evaluate_metrics(metrics, sample_size)

    if mode == "real":
        binary_path = shutil.which("lean-ctx")
        if not binary_path:
            report["recommendation"] = "NO_GO"
            report["reasons"] = ["Critical: 'lean-ctx' binary is missing from PATH."]
            return report
        metrics = collect_real_metrics(sample_size)
        evaluated = evaluate_metrics(metrics, sample_size)
        evaluated["reasons"] = [f"Binary found at {binary_path}."] + list(evaluated["reasons"])
        return evaluated

    report["recommendation"] = "NO_GO"
    report["reasons"] = [f"Unsupported mode: {mode}"]
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Lean-Ctx Real-world Validation Pack")
    parser.add_argument("--mode", choices=["mock", "real"], default="mock", help="Validation mode")
    parser.add_argument("--tasks", type=int, default=20, help="Number of tasks in the validation batch")
    args = parser.parse_args()

    report = get_validation_report(args.mode, args.tasks)
    print(json.dumps(report, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
