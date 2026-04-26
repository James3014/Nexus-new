#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Any

from scripts.bench.ab_eval import compare_datasets, load_runs


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _num(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"


def _wall_speedup(delta_sec: float, baseline_sec: float) -> str:
    if baseline_sec <= 0:
        return "n/a"
    return _pct(-delta_sec / baseline_sec)


def _token_status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("token_capture_status") or "unknown").strip().lower() or "unknown"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _count_text(counts: dict[str, int], key: str) -> str:
    return str(counts.get(key, 0))


def _scope_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    task_ids = {str(row.get("task_id") or "") for row in rows if row.get("task_id")}
    trials = {
        int(row.get("trial_index") or 1)
        for row in rows
        if str(row.get("trial_index") or "").strip()
    }
    return {
        "rows": len(rows),
        "unique_tasks": len(task_ids),
        "repeat_trials": max(trials) if trials else 1,
    }


def _public_token_claim_status(a: dict[str, Any], b: dict[str, Any], *, min_rate: float = 0.8) -> str:
    try:
        without_rate = float(a.get("token_measured_rate", 0.0) or 0.0)
        with_rate = float(b.get("token_measured_rate", 0.0) or 0.0)
    except (TypeError, ValueError):
        return "NO"
    return "YES" if without_rate >= min_rate and with_rate >= min_rate else "NO"


def render_markdown_report(
    *,
    without_path: str,
    with_path: str,
    label_without: str,
    label_with: str,
    benchmark_date: str,
) -> str:
    rows_without = load_runs(without_path)
    rows_with = load_runs(with_path)
    report = compare_datasets(
        label_without,
        rows_without,
        label_with,
        rows_with,
    )
    a = report["a"]["summary"]
    b = report["b"]["summary"]
    delta = report["delta"]
    formal = report["formal_treatment"]
    wall_delta = float(delta["avg_wall_duration_sec_delta"])
    baseline_wall = float(a["avg_wall_duration_sec"])
    token_without = _token_status_counts(rows_without)
    token_with = _token_status_counts(rows_with)
    without_scope = _scope_summary(rows_without)
    with_scope = _scope_summary(rows_with)
    token_public_safe = _public_token_claim_status(a, b)

    lines = [
        "# Gemini 3 Flash + Nexus Benchmark Report",
        "",
        f"- Date: {benchmark_date}",
        f"- Baseline: `{label_without}`",
        f"- Treatment: `{label_with}`",
        f"- Without Nexus: `{without_path}`",
        f"- With Nexus: `{with_path}`",
        f"- Without Nexus scope: {without_scope['unique_tasks']} unique tasks x {without_scope['repeat_trials']} trials = {without_scope['rows']} rows",
        f"- With Nexus scope: {with_scope['unique_tasks']} unique tasks x {with_scope['repeat_trials']} trials = {with_scope['rows']} rows",
        "",
        "## Result",
        "",
        "| Metric | Without Nexus | With Nexus | Delta |",
        "| --- | ---: | ---: | ---: |",
        f"| Solve rate | {_pct(a['solve_rate'])} | {_pct(b['solve_rate'])} | {_pct(delta['solve_rate_delta'])} |",
        f"| Semantic verified | {_pct(a['semantic_verified_rate'])} | {_pct(b['semantic_verified_rate'])} | {_pct(delta['semantic_verified_rate_delta'])} |",
        f"| Trust mismatch | {_pct(a['trust_mismatch_rate'])} | {_pct(b['trust_mismatch_rate'])} | {_pct(delta['trust_mismatch_rate_delta'])} |",
        f"| Avg wall time | {_num(a['avg_wall_duration_sec'])}s | {_num(b['avg_wall_duration_sec'])}s | {_num(wall_delta)}s |",
        f"| Wall speedup | n/a | {_wall_speedup(wall_delta, baseline_wall)} | n/a |",
        f"| Avg model calls | {_num(a['avg_model_calls'])} | {_num(b['avg_model_calls'])} | {_num(delta['avg_model_calls_delta'])} |",
        f"| Token measured rate | {_pct(a['token_measured_rate'])} | {_pct(b['token_measured_rate'])} | {_pct(delta['token_measured_rate_delta'])} |",
        f"| Token local-only rate | {_pct(a['token_local_only_rate'])} | {_pct(b['token_local_only_rate'])} | {_pct(delta['token_local_only_rate_delta'])} |",
        f"| Cost-comparable rate | {_pct(a['cost_comparable_rate'])} | {_pct(b['cost_comparable_rate'])} | {_pct(delta['cost_comparable_rate_delta'])} |",
        f"| Model token measured rate | {_pct(a['model_token_measured_rate'])} | {_pct(b['model_token_measured_rate'])} | {_pct(delta['model_token_measured_rate_delta'])} |",
        f"| Local rescue rate | {_pct(a['local_rescue_rate'])} | {_pct(b['local_rescue_rate'])} | {_pct(delta['local_rescue_rate_delta'])} |",
        f"| Token public-safe claim | {token_public_safe} | {token_public_safe} | n/a |",
        "",
        "## Token Telemetry",
        "",
        "| Token status | Without Nexus | With Nexus |",
        "| --- | ---: | ---: |",
        f"| measured | {_count_text(token_without, 'measured')} | {_count_text(token_with, 'measured')} |",
        f"| estimated | {_count_text(token_without, 'estimated')} | {_count_text(token_with, 'estimated')} |",
        f"| missing/unknown | {_count_text(token_without, 'missing')}/{_count_text(token_without, 'unknown')} | {_count_text(token_with, 'missing')}/{_count_text(token_with, 'unknown')} |",
        f"| not applicable local only | {_count_text(token_without, 'not_applicable_local_only')} | {_count_text(token_with, 'not_applicable_local_only')} |",
        "",
        "## Nexus Wearing Evidence",
        "",
        f"- Formal treatment valid: {formal['valid_count']}/{formal['total_runs']} ({_pct(formal['valid_rate'])})",
        f"- Gemini uses Nexus rate: {_pct(b['gemini_uses_nexus_rate'])}",
        f"- Nexus usage valid rate: {_pct(b['nexus_usage_valid_rate'])}",
        f"- Phase completion rate: {_pct(b['phase_completion_rate'])}",
        f"- Claim verified rate: {_pct(b['claim_verified_rate'])}",
        f"- Nexus rescue rate: {_pct(b['nexus_rescue_rate'])}",
        "",
        "## Public-Safe Claim",
        "",
        (
            f"On this fixed benchmark set, `{label_with}` improved solve rate from "
            f"{_pct(a['solve_rate'])} to {_pct(b['solve_rate'])} "
            f"({_pct(delta['solve_rate_delta'])} absolute) while keeping trust mismatch at "
            f"{_pct(b['trust_mismatch_rate'])}."
        ),
        "",
        "## Limits",
        "",
        "- Token/cost claims are not public-safe unless token measured rate is high enough for both arms.",
        "- Small samples need repeated trials before publication-grade claims.",
        "- This report proves benchmark-row evidence, not broad production generalization.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Gemini bare vs Gemini+Nexus benchmark markdown.")
    parser.add_argument("--without", required=True, help="Without-Nexus JSON/JSONL/CSV path")
    parser.add_argument("--with-nexus", required=True, help="With-Nexus JSON/JSONL/CSV path")
    parser.add_argument("--label-without", default="gemini_3_flash_bare")
    parser.add_argument("--label-with", default="gemini_3_flash_nexus")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--output", required=True, help="Markdown output path")
    args = parser.parse_args()

    markdown = render_markdown_report(
        without_path=args.without,
        with_path=args.with_nexus,
        label_without=args.label_without,
        label_with=args.label_with,
        benchmark_date=args.date,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
