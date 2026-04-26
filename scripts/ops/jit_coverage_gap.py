#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OBSERVATION_LOG = ROOT / ".nexus" / "reports" / "jit_observation.jsonl"
DEFAULT_REPORT = ROOT / ".nexus" / "reports" / "jit_coverage_gap.json"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _top(counter: Counter[str], limit: int) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def build_coverage_gap_report(rows: list[dict[str, Any]], *, limit: int = 10) -> dict[str, Any]:
    fallback_paths: Counter[str] = Counter()
    unmatched_paths: Counter[str] = Counter()
    high_risk_paths: Counter[str] = Counter()
    slow_targets: Counter[str] = Counter()
    fallback_runs = 0

    for row in rows:
        changed_paths = [str(path) for path in row.get("changed_paths", [])]
        if bool(row.get("fallback_used", False)):
            fallback_runs += 1
            fallback_paths.update(changed_paths)
        unmatched_paths.update(str(path) for path in row.get("unmatched_paths", []))
        if bool(row.get("high_risk_escalated", False)):
            high_risk_paths.update(changed_paths)
        durations = row.get("target_durations", {})
        if isinstance(durations, dict):
            for target, duration in durations.items():
                try:
                    duration_float = float(duration)
                except (TypeError, ValueError):
                    duration_float = 0.0
                if duration_float >= 1.0:
                    slow_targets[str(target)] += 1

    return {
        "schema": "nexus_jit_coverage_gap_v1",
        "observation_count": len(rows),
        "fallback_run_count": fallback_runs,
        "fallback_heavy_paths": _top(fallback_paths, limit),
        "unmatched_paths": _top(unmatched_paths, limit),
        "high_risk_paths": _top(high_risk_paths, limit),
        "slow_generic_targets": _top(slow_targets, limit),
        "ml_recommendation": "collect_more_observations_before_predictive_ranking",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize JIT observation gaps without ML ranking.")
    parser.add_argument("--input", default=str(DEFAULT_OBSERVATION_LOG))
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    parser.add_argument("--limit", type=int, default=10)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_coverage_gap_report(_read_jsonl(Path(args.input)), limit=max(1, int(args.limit)))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "SUCCESS", "output": str(out), "observation_count": report["observation_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
