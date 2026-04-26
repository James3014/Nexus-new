#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GRADE_RANK = {
    "WARN": 0,
    "B_PASS": 1,
    "A_PASS": 2,
    "S_PASS": 3,
    "S_PLUS": 4,
    "S2_PASS": 5,
    "S_ELITE": 6,
    "S3_PASS": 7,
    "S4_PASS": 8,
    "S5_PASS": 9,
    "S6_PASS": 10,
    "S7_PASS": 11,
    "S8_PASS": 12,
    "S9_PASS": 13,
    "S10_PASS": 14,
}


def _latest_file(glob_pattern: str) -> Path:
    files = sorted(Path(".").glob(glob_pattern), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"no_file_matched: {glob_pattern}")
    return files[-1].resolve()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid_json_payload: {path}")
    return payload


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _extract_metrics(s_grade: dict[str, Any]) -> dict[str, float | str]:
    summary = s_grade.get("summary", {}) if isinstance(s_grade.get("summary"), dict) else {}
    inputs = s_grade.get("inputs", {}) if isinstance(s_grade.get("inputs"), dict) else {}
    ops_kpi = inputs.get("ops_kpi_median_3round", {}) if isinstance(inputs.get("ops_kpi_median_3round"), dict) else {}
    anti_hall = inputs.get("anti_hallucination", {}) if isinstance(inputs.get("anti_hallucination"), dict) else {}
    capability = inputs.get("capability_paths", {}) if isinstance(inputs.get("capability_paths"), dict) else {}
    return {
        "verdict": str(summary.get("verdict", "WARN") or "WARN"),
        "pass_ratio": _num(summary.get("pass_ratio"), 0.0),
        "full_ab_weighted_score": _num(inputs.get("full_ab_weighted_score"), 0.0),
        "ops_overhead_p95_sec": _num(ops_kpi.get("wall_overhead_p95_sec"), 0.0),
        "ops_overhead_worst_decile_mean_sec": _num(ops_kpi.get("wall_overhead_worst_decile_mean_sec"), 0.0),
        "trust_mismatch_rate": _num(anti_hall.get("report_trust_mismatch_rate"), 0.0),
        "learn_citation_usage_rate": _num(capability.get("learn_mode_citation_usage_rate"), 1.0),
    }


def _extract_service_track(full_ab: dict[str, Any] | None) -> dict[str, float]:
    if not isinstance(full_ab, dict):
        return {}
    buckets = full_ab.get("buckets", [])
    if not isinstance(buckets, list):
        return {}
    out: dict[str, float] = {}
    for bucket in buckets:
        if not isinstance(bucket, dict):
            continue
        name = bucket.get("name")
        kpi = bucket.get("kpi")
        if not isinstance(name, str) or not isinstance(kpi, dict):
            continue
        key = name.replace("-", "_")
        out[f"{key}_delta_solve_rate"] = _num(kpi.get("delta_solve_rate"), 0.0)
        out[f"{key}_with_trust_mismatch_rate"] = _num(kpi.get("with_trust_mismatch_rate"), 1.0)
        out[f"{key}_wall_overhead_sec"] = _num(kpi.get("wall_overhead_sec"), 0.0)
        out[f"{key}_with_avg_duration_sec"] = _num(kpi.get("with_avg_duration_sec"), 0.0)
        out[f"{key}_without_avg_duration_sec"] = _num(kpi.get("without_avg_duration_sec"), 0.0)
        out[f"{key}_with_avg_wall_duration_sec"] = _num(kpi.get("with_avg_wall_duration_sec"), 0.0)
        out[f"{key}_without_avg_wall_duration_sec"] = _num(kpi.get("without_avg_wall_duration_sec"), 0.0)
        overhead_metric = str(kpi.get("overhead_metric", "avg_wall_duration_sec") or "avg_wall_duration_sec")
        if overhead_metric == "avg_duration_sec":
            denom = max(1e-6, out[f"{key}_without_avg_duration_sec"])
        else:
            denom = max(1e-6, out[f"{key}_without_avg_wall_duration_sec"])
        out[f"{key}_wall_overhead_ratio"] = out[f"{key}_wall_overhead_sec"] / denom
    out["weighted_score"] = _num(full_ab.get("weighted_score"), 0.0)
    return out


def evaluate_regression_guard(
    *,
    current_s_grade: dict[str, Any],
    baseline_s_grade: dict[str, Any] | None,
    service_full_ab: dict[str, Any] | None,
    min_grade: str,
    max_weighted_drop: float,
    max_pass_ratio_drop: float,
    max_overhead_p95_increase: float,
    max_overhead_worst_decile_increase: float,
    max_trust_mismatch_increase: float,
    max_learn_citation_drop: float,
    service_weighted_score_min: float,
    service_daily_delta_solve_rate_min: float,
    service_hard_delta_solve_rate_min: float,
    service_cross_delta_solve_rate_min: float,
    service_stress_delta_solve_rate_min: float,
    service_trust_mismatch_max: float,
    service_daily_wall_overhead_sec_max: float,
    service_hard_wall_overhead_sec_max: float,
    service_cross_wall_overhead_sec_max: float,
    service_stress_wall_overhead_sec_max: float,
    service_daily_wall_overhead_ratio_max: float = 0.5,
    service_hard_wall_overhead_ratio_max: float = 0.5,
    service_cross_wall_overhead_ratio_max: float = 0.6,
    service_stress_wall_overhead_ratio_max: float = 0.6,
) -> dict[str, Any]:
    current = _extract_metrics(current_s_grade)
    min_rank = GRADE_RANK.get(min_grade, GRADE_RANK["S6_PASS"])
    current_rank = GRADE_RANK.get(str(current["verdict"]), -1)
    failures: list[str] = []

    if current_rank < min_rank:
        failures.append(f"grade_below_min: current={current['verdict']} min={min_grade}")

    baseline_metrics = _extract_metrics(baseline_s_grade) if baseline_s_grade else None
    if baseline_metrics:
        weighted_drop = _num(baseline_metrics["full_ab_weighted_score"]) - _num(current["full_ab_weighted_score"])
        pass_ratio_drop = _num(baseline_metrics["pass_ratio"]) - _num(current["pass_ratio"])
        overhead_p95_increase = _num(current["ops_overhead_p95_sec"]) - _num(baseline_metrics["ops_overhead_p95_sec"])
        overhead_worst_increase = _num(current["ops_overhead_worst_decile_mean_sec"]) - _num(
            baseline_metrics["ops_overhead_worst_decile_mean_sec"]
        )
        trust_mismatch_increase = _num(current["trust_mismatch_rate"]) - _num(baseline_metrics["trust_mismatch_rate"])
        citation_drop = _num(baseline_metrics["learn_citation_usage_rate"]) - _num(current["learn_citation_usage_rate"])

        if weighted_drop > max_weighted_drop:
            failures.append(f"weighted_score_drop: drop={weighted_drop:.4f} allowed={max_weighted_drop:.4f}")
        if pass_ratio_drop > max_pass_ratio_drop:
            failures.append(f"pass_ratio_drop: drop={pass_ratio_drop:.4f} allowed={max_pass_ratio_drop:.4f}")
        if overhead_p95_increase > max_overhead_p95_increase:
            failures.append(
                f"ops_overhead_p95_regression: increase={overhead_p95_increase:.4f}s allowed={max_overhead_p95_increase:.4f}s"
            )
        if overhead_worst_increase > max_overhead_worst_decile_increase:
            failures.append(
                f"ops_overhead_worst_decile_regression: increase={overhead_worst_increase:.4f}s allowed={max_overhead_worst_decile_increase:.4f}s"
            )
        if trust_mismatch_increase > max_trust_mismatch_increase:
            failures.append(
                f"trust_mismatch_regression: increase={trust_mismatch_increase:.4f} allowed={max_trust_mismatch_increase:.4f}"
            )
        if citation_drop > max_learn_citation_drop:
            failures.append(f"learn_citation_usage_regression: drop={citation_drop:.4f} allowed={max_learn_citation_drop:.4f}")

    service_track = _extract_service_track(service_full_ab)
    if service_track:
        if _num(service_track.get("weighted_score")) < service_weighted_score_min:
            failures.append(
                f"service_weighted_score_below_min: current={_num(service_track.get('weighted_score')):.4f} min={service_weighted_score_min:.4f}"
            )
        if _num(service_track.get("daily_delta_solve_rate")) < service_daily_delta_solve_rate_min:
            failures.append(
                f"service_daily_delta_solve_rate_below_min: current={_num(service_track.get('daily_delta_solve_rate')):.4f} min={service_daily_delta_solve_rate_min:.4f}"
            )
        if _num(service_track.get("hard_delta_solve_rate")) < service_hard_delta_solve_rate_min:
            failures.append(
                f"service_hard_delta_solve_rate_below_min: current={_num(service_track.get('hard_delta_solve_rate')):.4f} min={service_hard_delta_solve_rate_min:.4f}"
            )
        if _num(service_track.get("cross_module_delta_solve_rate")) < service_cross_delta_solve_rate_min:
            failures.append(
                f"service_cross_delta_solve_rate_below_min: current={_num(service_track.get('cross_module_delta_solve_rate')):.4f} min={service_cross_delta_solve_rate_min:.4f}"
            )
        if _num(service_track.get("cross_module_stress_delta_solve_rate")) < service_stress_delta_solve_rate_min:
            failures.append(
                f"service_stress_delta_solve_rate_below_min: current={_num(service_track.get('cross_module_stress_delta_solve_rate')):.4f} min={service_stress_delta_solve_rate_min:.4f}"
            )
        for field in (
            "daily_with_trust_mismatch_rate",
            "hard_with_trust_mismatch_rate",
            "cross_module_with_trust_mismatch_rate",
            "cross_module_stress_with_trust_mismatch_rate",
        ):
            if _num(service_track.get(field)) > service_trust_mismatch_max:
                failures.append(f"{field}_above_max: current={_num(service_track.get(field)):.4f} max={service_trust_mismatch_max:.4f}")
        if _num(service_track.get("daily_wall_overhead_sec")) > service_daily_wall_overhead_sec_max:
            failures.append(
                f"service_daily_wall_overhead_above_max: current={_num(service_track.get('daily_wall_overhead_sec')):.4f}s max={service_daily_wall_overhead_sec_max:.4f}s"
            )
        if _num(service_track.get("hard_wall_overhead_sec")) > service_hard_wall_overhead_sec_max:
            failures.append(
                f"service_hard_wall_overhead_above_max: current={_num(service_track.get('hard_wall_overhead_sec')):.4f}s max={service_hard_wall_overhead_sec_max:.4f}s"
            )
        if _num(service_track.get("cross_module_wall_overhead_sec")) > service_cross_wall_overhead_sec_max:
            failures.append(
                f"service_cross_wall_overhead_above_max: current={_num(service_track.get('cross_module_wall_overhead_sec')):.4f}s max={service_cross_wall_overhead_sec_max:.4f}s"
            )
        if _num(service_track.get("cross_module_stress_wall_overhead_sec")) > service_stress_wall_overhead_sec_max:
            failures.append(
                f"service_stress_wall_overhead_above_max: current={_num(service_track.get('cross_module_stress_wall_overhead_sec')):.4f}s max={service_stress_wall_overhead_sec_max:.4f}s"
            )
        if (
            _num(service_track.get("daily_wall_overhead_sec")) > service_daily_wall_overhead_sec_max
            and _num(service_track.get("daily_wall_overhead_ratio")) > service_daily_wall_overhead_ratio_max
        ):
            failures.append(
                f"service_daily_wall_overhead_ratio_above_max: current={_num(service_track.get('daily_wall_overhead_ratio')):.4f} max={service_daily_wall_overhead_ratio_max:.4f}"
            )
        if (
            _num(service_track.get("hard_wall_overhead_sec")) > service_hard_wall_overhead_sec_max
            and _num(service_track.get("hard_wall_overhead_ratio")) > service_hard_wall_overhead_ratio_max
        ):
            failures.append(
                f"service_hard_wall_overhead_ratio_above_max: current={_num(service_track.get('hard_wall_overhead_ratio')):.4f} max={service_hard_wall_overhead_ratio_max:.4f}"
            )
        if (
            _num(service_track.get("cross_module_wall_overhead_sec")) > service_cross_wall_overhead_sec_max
            and _num(service_track.get("cross_module_wall_overhead_ratio")) > service_cross_wall_overhead_ratio_max
        ):
            failures.append(
                f"service_cross_wall_overhead_ratio_above_max: current={_num(service_track.get('cross_module_wall_overhead_ratio')):.4f} max={service_cross_wall_overhead_ratio_max:.4f}"
            )
        if (
            _num(service_track.get("cross_module_stress_wall_overhead_sec")) > service_stress_wall_overhead_sec_max
            and _num(service_track.get("cross_module_stress_wall_overhead_ratio")) > service_stress_wall_overhead_ratio_max
        ):
            failures.append(
                f"service_stress_wall_overhead_ratio_above_max: current={_num(service_track.get('cross_module_stress_wall_overhead_ratio')):.4f} max={service_stress_wall_overhead_ratio_max:.4f}"
            )

    status = "PASS" if not failures else "FAIL"
    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_grade": min_grade,
        "current": current,
        "baseline": baseline_metrics,
        "service_track": service_track,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard against benchmark regressions across S-grade reports.")
    parser.add_argument("--current-s-grade-file", default="")
    parser.add_argument("--baseline-s-grade-file", default=".nexus/reports/bench/s_grade/s_grade_baseline.json")
    parser.add_argument("--service-full-ab-file", default="")
    parser.add_argument("--min-grade", default="S9_PASS")
    parser.add_argument("--max-weighted-drop", type=float, default=0.01)
    parser.add_argument("--max-pass-ratio-drop", type=float, default=0.03)
    parser.add_argument("--max-overhead-p95-increase", type=float, default=0.10)
    parser.add_argument("--max-overhead-worst-decile-increase", type=float, default=0.10)
    parser.add_argument("--max-trust-mismatch-increase", type=float, default=0.0)
    parser.add_argument("--max-learn-citation-drop", type=float, default=0.10)
    parser.add_argument("--service-weighted-score-min", type=float, default=0.55)
    parser.add_argument("--service-daily-delta-solve-rate-min", type=float, default=-0.02)
    parser.add_argument("--service-hard-delta-solve-rate-min", type=float, default=-0.02)
    parser.add_argument("--service-cross-delta-solve-rate-min", type=float, default=-0.02)
    parser.add_argument("--service-stress-delta-solve-rate-min", type=float, default=-0.02)
    parser.add_argument("--service-trust-mismatch-max", type=float, default=0.0)
    parser.add_argument("--service-daily-wall-overhead-sec-max", type=float, default=1.2)
    parser.add_argument("--service-hard-wall-overhead-sec-max", type=float, default=1.2)
    parser.add_argument("--service-cross-wall-overhead-sec-max", type=float, default=1.5)
    parser.add_argument("--service-stress-wall-overhead-sec-max", type=float, default=1.5)
    parser.add_argument("--service-daily-wall-overhead-ratio-max", type=float, default=0.5)
    parser.add_argument("--service-hard-wall-overhead-ratio-max", type=float, default=0.5)
    parser.add_argument("--service-cross-wall-overhead-ratio-max", type=float, default=0.6)
    parser.add_argument("--service-stress-wall-overhead-ratio-max", type=float, default=0.6)
    parser.add_argument("--write-baseline-on-pass", action="store_true")
    parser.add_argument("--output-file", default="")
    parser.add_argument("--output-json", action="store_true")
    args = parser.parse_args()

    current_file = Path(args.current_s_grade_file).resolve() if args.current_s_grade_file else _latest_file(".nexus/reports/bench/s_grade/s_grade_report_*.json")
    baseline_file = Path(args.baseline_s_grade_file).resolve()
    service_full_ab_file = Path(args.service_full_ab_file).resolve() if args.service_full_ab_file else None

    current_payload = _load_json(current_file)
    baseline_payload = _load_json(baseline_file) if baseline_file.exists() else None
    service_full_ab_payload = _load_json(service_full_ab_file) if service_full_ab_file and service_full_ab_file.exists() else None

    result = evaluate_regression_guard(
        current_s_grade=current_payload,
        baseline_s_grade=baseline_payload,
        service_full_ab=service_full_ab_payload,
        min_grade=str(args.min_grade),
        max_weighted_drop=float(args.max_weighted_drop),
        max_pass_ratio_drop=float(args.max_pass_ratio_drop),
        max_overhead_p95_increase=float(args.max_overhead_p95_increase),
        max_overhead_worst_decile_increase=float(args.max_overhead_worst_decile_increase),
        max_trust_mismatch_increase=float(args.max_trust_mismatch_increase),
        max_learn_citation_drop=float(args.max_learn_citation_drop),
        service_weighted_score_min=float(args.service_weighted_score_min),
        service_daily_delta_solve_rate_min=float(args.service_daily_delta_solve_rate_min),
        service_hard_delta_solve_rate_min=float(args.service_hard_delta_solve_rate_min),
        service_cross_delta_solve_rate_min=float(args.service_cross_delta_solve_rate_min),
        service_stress_delta_solve_rate_min=float(args.service_stress_delta_solve_rate_min),
        service_trust_mismatch_max=float(args.service_trust_mismatch_max),
        service_daily_wall_overhead_sec_max=float(args.service_daily_wall_overhead_sec_max),
        service_hard_wall_overhead_sec_max=float(args.service_hard_wall_overhead_sec_max),
        service_cross_wall_overhead_sec_max=float(args.service_cross_wall_overhead_sec_max),
        service_stress_wall_overhead_sec_max=float(args.service_stress_wall_overhead_sec_max),
        service_daily_wall_overhead_ratio_max=float(args.service_daily_wall_overhead_ratio_max),
        service_hard_wall_overhead_ratio_max=float(args.service_hard_wall_overhead_ratio_max),
        service_cross_wall_overhead_ratio_max=float(args.service_cross_wall_overhead_ratio_max),
        service_stress_wall_overhead_ratio_max=float(args.service_stress_wall_overhead_ratio_max),
    )
    result["sources"] = {
        "current_s_grade_file": str(current_file),
        "baseline_s_grade_file": str(baseline_file) if baseline_file.exists() else "",
        "service_full_ab_file": str(service_full_ab_file) if service_full_ab_file and service_full_ab_file.exists() else "",
    }

    out_file = Path(args.output_file).resolve() if args.output_file else Path(".nexus/reports/bench/guard").resolve() / f"regression_guard_{int(time.time())}.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    result["report_file"] = str(out_file)

    if result["status"] == "PASS" and args.write_baseline_on_pass:
        baseline_file.parent.mkdir(parents=True, exist_ok=True)
        baseline_file.write_text(json.dumps(current_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        result["baseline_updated"] = True
    else:
        result["baseline_updated"] = False

    if args.output_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Regression guard: {result['status']} ({len(result['failures'])} failures)")
        print(f"Report: {out_file}")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
