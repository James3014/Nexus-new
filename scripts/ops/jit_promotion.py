#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OBSERVATION_LOG = ROOT / ".nexus" / "reports" / "jit_observation.jsonl"
DEFAULT_HISTORY = ROOT / ".nexus" / "reports" / "test_history.jsonl"
DEFAULT_MISSED_REPORT = ROOT / ".nexus" / "reports" / "jit_missed_candidates.json"
DEFAULT_STATS = ROOT / ".nexus" / "test_impact_stats.json"
DEFAULT_OUTPUT = ROOT / ".nexus" / "reports" / "jit_predictive_promotion_report.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
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


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _stats_target_count(stats_payload: dict[str, Any]) -> int:
    mappings = stats_payload.get("mappings", {})
    if not isinstance(mappings, dict):
        return 0
    targets: set[str] = set()
    for target_map in mappings.values():
        if isinstance(target_map, dict):
            targets.update(str(target) for target in target_map)
    return len(targets)


def build_promotion_report(
    observation_rows: list[dict[str, Any]],
    history_rows: list[dict[str, Any]],
    missed_report: dict[str, Any],
    stats_payload: dict[str, Any],
    *,
    min_observations: int = 20,
    min_nightly_full: int = 3,
    max_miss_rate: float = 0.0,
    max_fallback_run_rate: float = 0.25,
    max_unmatched_path_rate: float = 0.05,
    selector_default_ranking: str = "static",
) -> dict[str, Any]:
    eligible_observations = [
        row
        for row in observation_rows
        if str(row.get("event") or row.get("mode") or "") in {"changed_only", "changed-only"}
        or (row.get("changed_paths") and row.get("targets"))
    ]
    nightly_full_count = sum(
        1 for row in history_rows if str(row.get("mode") or row.get("event") or "") == "nightly-full"
    )
    changed_path_count = sum(len(row.get("changed_paths", []) or []) for row in eligible_observations)
    fallback_count = sum(1 for row in eligible_observations if bool(row.get("fallback_used", False)))
    unmatched_path_count = sum(len(row.get("unmatched_paths", []) or []) for row in eligible_observations)
    missed_count = int(missed_report.get("missed_count", 0) or 0)
    predictive_saved_runtime_sec = round(
        sum(float(row.get("predictive_saved_runtime_sec", 0.0) or 0.0) for row in eligible_observations),
        4,
    )
    miss_rate = _rate(missed_count, nightly_full_count)
    fallback_run_rate = _rate(fallback_count, len(eligible_observations))
    unmatched_path_rate = _rate(unmatched_path_count, changed_path_count)
    static_default_unchanged = selector_default_ranking == "static"
    criteria = {
        "eligible_observation_count": len(eligible_observations) >= min_observations,
        "nightly_full_count": nightly_full_count >= min_nightly_full,
        "miss_rate": miss_rate is not None and miss_rate <= max_miss_rate,
        "fallback_run_rate": fallback_run_rate is not None and fallback_run_rate <= max_fallback_run_rate,
        "unmatched_path_rate": unmatched_path_rate is not None and unmatched_path_rate <= max_unmatched_path_rate,
        "predictive_saved_runtime_sec": predictive_saved_runtime_sec > 0,
        "static_default_unchanged": static_default_unchanged,
    }
    verdict = "PROMOTE_CANDIDATE" if all(criteria.values()) else "HOLD"
    return {
        "schema": "nexus_jit_predictive_promotion_v1",
        "verdict": verdict,
        "trial_lane_allowed": verdict == "PROMOTE_CANDIDATE",
        "default_switch_allowed": False,
        "default_switch_reason": "requires_sustained_observation_window",
        "criteria": criteria,
        "thresholds": {
            "min_observations": min_observations,
            "min_nightly_full": min_nightly_full,
            "max_miss_rate": max_miss_rate,
            "max_fallback_run_rate": max_fallback_run_rate,
            "max_unmatched_path_rate": max_unmatched_path_rate,
        },
        "eligible_observation_count": len(eligible_observations),
        "nightly_full_count": nightly_full_count,
        "missed_count": missed_count,
        "miss_rate": miss_rate,
        "fallback_count": fallback_count,
        "fallback_run_rate": fallback_run_rate,
        "unmatched_path_count": unmatched_path_count,
        "unmatched_path_rate": unmatched_path_rate,
        "predictive_saved_runtime_sec": predictive_saved_runtime_sec,
        "static_default_unchanged": static_default_unchanged,
        "stats_target_count": _stats_target_count(stats_payload),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate whether JIT predictive ranking can be promoted.")
    parser.add_argument("--observations", default=str(DEFAULT_OBSERVATION_LOG))
    parser.add_argument("--history", default=str(DEFAULT_HISTORY))
    parser.add_argument("--missed-report", default=str(DEFAULT_MISSED_REPORT))
    parser.add_argument("--stats", default=str(DEFAULT_STATS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--min-observations", type=int, default=20)
    parser.add_argument("--min-nightly-full", type=int, default=3)
    parser.add_argument("--max-miss-rate", type=float, default=0.0)
    parser.add_argument("--max-fallback-run-rate", type=float, default=0.25)
    parser.add_argument("--max-unmatched-path-rate", type=float, default=0.05)
    parser.add_argument("--selector-default-ranking", default="static")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_promotion_report(
        read_jsonl(Path(args.observations)),
        read_jsonl(Path(args.history)),
        read_json(Path(args.missed_report)),
        read_json(Path(args.stats)),
        min_observations=args.min_observations,
        min_nightly_full=args.min_nightly_full,
        max_miss_rate=args.max_miss_rate,
        max_fallback_run_rate=args.max_fallback_run_rate,
        max_unmatched_path_rate=args.max_unmatched_path_rate,
        selector_default_ranking=args.selector_default_ranking,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "SUCCESS", "output": str(output), "verdict": report["verdict"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
