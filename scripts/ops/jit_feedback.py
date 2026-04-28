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


def _failed_targets(row: dict[str, Any]) -> list[str]:
    metadata = row.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    for key in ("failed_targets", "failing_targets"):
        value = row.get(key, metadata.get(key))
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
    if row.get("success") is False:
        return [str(item) for item in row.get("targets", []) if str(item).strip()]
    return []


def build_missed_candidates(history_rows: list[dict[str, Any]]) -> dict[str, Any]:
    last_changed_only: dict[str, Any] | None = None
    missed: list[dict[str, Any]] = []
    for row in history_rows:
        mode = str(row.get("mode") or row.get("event") or "")
        if mode in {"changed-only", "changed_only"}:
            last_changed_only = row
            continue
        if mode != "nightly-full":
            continue
        failing = _failed_targets(row)
        if not failing or not last_changed_only:
            continue
        selected = {str(target) for target in last_changed_only.get("targets", [])}
        for target in failing:
            if target not in selected:
                metadata = last_changed_only.get("metadata", {})
                if not isinstance(metadata, dict):
                    metadata = {}
                missed.append(
                    {
                        "target": target,
                        "changed_paths": metadata.get("changed_paths", []),
                        "selected_targets": sorted(selected),
                        "nightly_timestamp": row.get("timestamp", ""),
                        "changed_only_timestamp": last_changed_only.get("timestamp", ""),
                    }
                )
    return {
        "schema": "nexus_jit_missed_candidates_v1",
        "missed_count": len(missed),
        "missed_candidates": missed,
    }


def build_impact_stats(
    observation_rows: list[dict[str, Any]],
    missed_report: dict[str, Any],
) -> dict[str, Any]:
    mappings: dict[str, dict[str, Any]] = {}
    for row in observation_rows:
        changed_paths = [str(path) for path in row.get("changed_paths", []) if str(path).strip()]
        targets = [str(target) for target in row.get("targets", []) if str(target).strip()]
        success = bool(row.get("success", False))
        durations = row.get("target_durations", {})
        if not isinstance(durations, dict):
            durations = {}
        for path in changed_paths:
            path_bucket = mappings.setdefault(path, {})
            for target in targets:
                bucket = path_bucket.setdefault(
                    target,
                    {"runs": 0, "failures": 0, "missed_count": 0, "duration_total_sec": 0.0, "duration_samples": 0},
                )
                bucket["runs"] += 1
                if not success:
                    bucket["failures"] += 1
                try:
                    duration = float(durations.get(target, 0.0) or 0.0)
                except (TypeError, ValueError):
                    duration = 0.0
                if duration > 0:
                    bucket["duration_total_sec"] += duration
                    bucket["duration_samples"] += 1
    for miss in missed_report.get("missed_candidates", []):
        target = str(miss.get("target", ""))
        for path in miss.get("changed_paths", []):
            path_bucket = mappings.setdefault(str(path), {})
            bucket = path_bucket.setdefault(
                target,
                {"runs": 0, "failures": 0, "missed_count": 0, "duration_total_sec": 0.0, "duration_samples": 0},
            )
            bucket["missed_count"] += 1

    normalized: dict[str, dict[str, Any]] = {}
    for path, targets in mappings.items():
        normalized[path] = {}
        for target, bucket in targets.items():
            runs = int(bucket["runs"])
            failures = int(bucket["failures"])
            missed_count = int(bucket["missed_count"])
            samples = int(bucket["duration_samples"])
            avg_duration = round(float(bucket["duration_total_sec"]) / samples, 4) if samples else 0.0
            score = round(runs * 1.0 + failures * 2.0 + missed_count * 3.0 - min(avg_duration / 10.0, 2.0), 4)
            normalized[path][target] = {
                "runs": runs,
                "failures": failures,
                "missed_count": missed_count,
                "avg_duration_sec": avg_duration,
                "score": score,
                "score_reasons": {
                    "historical_runs": runs,
                    "historical_failures": failures,
                    "missed_candidate": missed_count,
                    "duration_penalty": round(min(avg_duration / 10.0, 2.0), 4),
                },
            }
    return {"schema": "nexus_test_impact_stats_v1", "mappings": normalized}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build JIT feedback reports without changing selector defaults.")
    parser.add_argument("--observations", default=str(DEFAULT_OBSERVATION_LOG))
    parser.add_argument("--history", default=str(DEFAULT_HISTORY))
    parser.add_argument("--missed-output", default=str(DEFAULT_MISSED_REPORT))
    parser.add_argument("--stats-output", default=str(DEFAULT_STATS))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    missed = build_missed_candidates(read_jsonl(Path(args.history)))
    stats = build_impact_stats(read_jsonl(Path(args.observations)), missed)
    missed_path = Path(args.missed_output)
    stats_path = Path(args.stats_output)
    missed_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    missed_path.write_text(json.dumps(missed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    stats_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "SUCCESS", "missed_output": str(missed_path), "stats_output": str(stats_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
