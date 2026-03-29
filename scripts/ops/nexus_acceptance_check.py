#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CriterionResult:
    name: str
    passed: bool
    detail: dict[str, Any]


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _pct(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 2)


def _window_pair(rows: list[dict[str, Any]], window: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if window <= 0:
        return rows, []
    recent = rows[-window:]
    previous = rows[-(window * 2) : -window] if len(rows) > window else []
    return recent, previous


def _evaluate_repair_success(
    optimization_rows: list[dict[str, Any]],
    *,
    window: int,
    success_min: float,
) -> CriterionResult:
    recent = optimization_rows[-window:] if window > 0 else optimization_rows
    total = len(recent)
    success = sum(1 for row in recent if bool(row.get("success", False)))
    rate = _pct(success, total)
    passed = total > 0 and rate >= success_min
    detail = {
        "window_rows": total,
        "success_count": success,
        "success_rate": rate,
        "threshold": success_min,
    }
    return CriterionResult(
        name="auto_repair_success_rate",
        passed=passed,
        detail=detail,
    )


def _phantom_fp_rate(rows: list[dict[str, Any]]) -> tuple[float, int]:
    phantom_blocked = [row for row in rows if bool(row.get("phantom_blocked", False))]
    blocked_count = len(phantom_blocked)
    if blocked_count == 0:
        return 0.0, 0
    false_positive = sum(1 for row in phantom_blocked if bool(row.get("pass", False)))
    return _pct(false_positive, blocked_count), blocked_count


def _evaluate_phantom_false_positive(
    outcome_rows: list[dict[str, Any]],
    *,
    window: int,
    fp_max: float,
) -> CriterionResult:
    recent, previous = _window_pair(outcome_rows, window)
    recent_rate, recent_blocked = _phantom_fp_rate(recent)
    prev_rate, prev_blocked = _phantom_fp_rate(previous)

    trend_ok = recent_rate <= prev_rate if previous else True
    threshold_ok = recent_rate <= fp_max
    passed = trend_ok and threshold_ok
    detail = {
        "recent_window_rows": len(recent),
        "previous_window_rows": len(previous),
        "recent_phantom_blocked": recent_blocked,
        "previous_phantom_blocked": prev_blocked,
        "recent_false_positive_rate": recent_rate,
        "previous_false_positive_rate": prev_rate,
        "threshold": fp_max,
    }
    return CriterionResult(
        name="phantom_false_positive_rate",
        passed=passed,
        detail=detail,
    )


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _evaluate_regression_and_side_effects(
    outcome_rows: list[dict[str, Any]],
    *,
    window: int,
    regression_min: float,
    retry_spike_factor: float,
    retry_abs_max: float,
) -> CriterionResult:
    recent, previous = _window_pair(outcome_rows, window)
    recent_reg = _avg([float(row.get("regression_pass_rate", 0.0) or 0.0) for row in recent])
    prev_reg = _avg([float(row.get("regression_pass_rate", 0.0) or 0.0) for row in previous])

    recent_retry = _avg(
        [
            float(row.get("retry_count", 0.0) or 0.0)
            + float(row.get("self_heal_retry_count", 0.0) or 0.0)
            for row in recent
        ]
    )
    prev_retry = _avg(
        [
            float(row.get("retry_count", 0.0) or 0.0)
            + float(row.get("self_heal_retry_count", 0.0) or 0.0)
            for row in previous
        ]
    )

    regression_ok = recent_reg >= regression_min
    if previous:
        side_effect_spike = recent_retry > max(retry_abs_max, prev_retry * retry_spike_factor)
    else:
        side_effect_spike = recent_retry > retry_abs_max

    passed = regression_ok and not side_effect_spike
    detail = {
        "recent_window_rows": len(recent),
        "previous_window_rows": len(previous),
        "recent_regression_pass_rate_avg": recent_reg,
        "previous_regression_pass_rate_avg": prev_reg,
        "regression_threshold": regression_min,
        "recent_retry_avg": recent_retry,
        "previous_retry_avg": prev_retry,
        "retry_abs_max": retry_abs_max,
        "retry_spike_factor": retry_spike_factor,
        "side_effect_spike": side_effect_spike,
    }
    return CriterionResult(
        name="regression_and_side_effect",
        passed=passed,
        detail=detail,
    )


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines: list[str] = []
    lines.append("# Nexus Acceptance Check")
    lines.append("")
    lines.append(f"- status: {report['status']}")
    lines.append(f"- gate_passed: {str(report['gate_passed']).lower()}")
    lines.append(f"- generated_at_utc: {report['generated_at_utc']}")
    lines.append("")
    lines.append("## Criteria")
    lines.append("")
    for item in report["criteria"]:
        lines.append(f"- {item['name']}: {'PASS' if item['passed'] else 'FAIL'}")
        for key, value in item["detail"].items():
            lines.append(f"  - {key}: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fixed 3-rule acceptance checks and emit reports.")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--output-dir", default=".nexus/reports")
    parser.add_argument("--window", type=int, default=50)
    parser.add_argument("--repair-success-min", type=float, default=80.0)
    parser.add_argument("--phantom-fp-max", type=float, default=3.0)
    parser.add_argument("--regression-pass-min", type=float, default=95.0)
    parser.add_argument("--retry-spike-factor", type=float, default=2.0)
    parser.add_argument("--retry-abs-max", type=float, default=1.0)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    output_dir = (project_root / args.output_dir).resolve() if not str(args.output_dir).startswith("/") else Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics_dir = project_root / ".nexus" / "metrics"
    optimization_rows = _load_jsonl(metrics_dir / "skills_optimization_runs.jsonl")
    outcome_rows = _load_jsonl(metrics_dir / "skill_outcome_events.jsonl")

    checks = [
        _evaluate_repair_success(
            optimization_rows,
            window=args.window,
            success_min=args.repair_success_min,
        ),
        _evaluate_phantom_false_positive(
            outcome_rows,
            window=args.window,
            fp_max=args.phantom_fp_max,
        ),
        _evaluate_regression_and_side_effects(
            outcome_rows,
            window=args.window,
            regression_min=args.regression_pass_min,
            retry_spike_factor=args.retry_spike_factor,
            retry_abs_max=args.retry_abs_max,
        ),
    ]

    gate_passed = all(check.passed for check in checks)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if gate_passed else "FAIL",
        "gate_passed": gate_passed,
        "project_root": str(project_root),
        "input": {
            "window": args.window,
            "repair_success_min": args.repair_success_min,
            "phantom_fp_max": args.phantom_fp_max,
            "regression_pass_min": args.regression_pass_min,
            "retry_spike_factor": args.retry_spike_factor,
            "retry_abs_max": args.retry_abs_max,
        },
        "sources": {
            "skills_optimization_runs": str(metrics_dir / "skills_optimization_runs.jsonl"),
            "skill_outcome_events": str(metrics_dir / "skill_outcome_events.jsonl"),
        },
        "criteria": [
            {"name": check.name, "passed": check.passed, "detail": check.detail}
            for check in checks
        ],
    }

    json_path = output_dir / "acceptance_check.json"
    md_path = output_dir / "acceptance_check.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(report, md_path)

    print(f"[acceptance-check] status={report['status']}")
    print(f"[acceptance-check] gate_passed={str(report['gate_passed']).lower()}")
    print(f"[acceptance-check] json={json_path}")
    print(f"[acceptance-check] report={md_path}")
    return 0 if gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
