#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _rate(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for row in rows if bool(row.get(key))) / len(rows), 4)


def _avg(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    total = 0.0
    for row in rows:
        try:
            total += float(row.get(key, 0.0) or 0.0)
        except Exception:
            pass
    return round(total / len(rows), 4)


def _status_rate(rows: list[dict[str, Any]], key: str, expected: str) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for row in rows if str(row.get(key) or "") == expected) / len(rows), 4)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_runs": len(rows),
        "verified_solve_rate": _rate(rows, "verified_solve"),
        "semantic_verified_rate": _rate(rows, "semantic_verified"),
        "root_cause_accuracy": _rate(rows, "root_cause_accurate"),
        "regression_test_added_rate": _rate(rows, "regression_test_added"),
        "unrelated_change_rate": _rate(rows, "unrelated_change"),
        "trust_mismatch_rate": _rate(rows, "trust_mismatch"),
        "rollback_safety_rate": _rate(rows, "rollback_safe"),
        "learning_reuse_rate": _rate(rows, "learning_reused"),
        "compare_verified_rate": _status_rate(rows, "nexus_compare_status", "VERIFIED"),
        "compare_partial_rate": _status_rate(rows, "nexus_compare_status", "PARTIAL"),
        "avg_duration_sec": _avg(rows, "duration_sec"),
        "avg_tokens": _avg(rows, "total_tokens"),
    }


def grade(delta: dict[str, float], with_summary: dict[str, Any], overhead_ratio: float) -> str:
    if (
        with_summary["verified_solve_rate"] >= 0.9
        and with_summary["trust_mismatch_rate"] == 0.0
        and with_summary["unrelated_change_rate"] == 0.0
        and overhead_ratio <= 1.5
    ):
        return "REALISM_S10"
    if with_summary["unrelated_change_rate"] == 0.0 and with_summary["rollback_safety_rate"] >= 1.0:
        return "REALISM_S5"
    if with_summary["root_cause_accuracy"] >= 0.75:
        return "REALISM_S4"
    if with_summary["regression_test_added_rate"] >= 0.8:
        return "REALISM_S3"
    if delta["verified_solve_rate_delta"] >= 0.2 and with_summary["unrelated_change_rate"] <= 0.03:
        return "REALISM_S2"
    if delta["verified_solve_rate_delta"] >= 0.15 and with_summary["trust_mismatch_rate"] <= 0.05:
        return "REALISM_S1"
    return "REALISM_WARN"


def compare(with_rows: list[dict[str, Any]], without_rows: list[dict[str, Any]]) -> dict[str, Any]:
    with_summary = summarize(with_rows)
    without_summary = summarize(without_rows)
    delta = {
        "verified_solve_rate_delta": round(with_summary["verified_solve_rate"] - without_summary["verified_solve_rate"], 4),
        "semantic_verified_rate_delta": round(with_summary["semantic_verified_rate"] - without_summary["semantic_verified_rate"], 4),
        "root_cause_accuracy_delta": round(with_summary["root_cause_accuracy"] - without_summary["root_cause_accuracy"], 4),
        "regression_test_added_rate_delta": round(
            with_summary["regression_test_added_rate"] - without_summary["regression_test_added_rate"], 4
        ),
        "unrelated_change_rate_delta": round(without_summary["unrelated_change_rate"] - with_summary["unrelated_change_rate"], 4),
        "trust_mismatch_rate_delta": round(without_summary["trust_mismatch_rate"] - with_summary["trust_mismatch_rate"], 4),
        "rollback_safety_rate_delta": round(with_summary["rollback_safety_rate"] - without_summary["rollback_safety_rate"], 4),
        "learning_reuse_rate_delta": round(with_summary["learning_reuse_rate"] - without_summary["learning_reuse_rate"], 4),
    }
    overhead_ratio = round(with_summary["avg_duration_sec"] / max(0.001, without_summary["avg_duration_sec"]), 4)
    return {
        "status": "SUCCESS",
        "with_nexus": with_summary,
        "without_nexus": without_summary,
        "delta": delta,
        "time_overhead_ratio": overhead_ratio,
        "nexus_realism_grade": grade(delta, with_summary, overhead_ratio),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate real-world Nexus coding harness A/B rows.")
    parser.add_argument("--with-file", required=True)
    parser.add_argument("--without-file", required=True)
    parser.add_argument("--output-file", default="")
    parser.add_argument("--output-json", action="store_true")
    args = parser.parse_args()
    payload = compare(_load_jsonl(args.with_file), _load_jsonl(args.without_file))
    if args.output_file:
        out = Path(args.output_file)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        payload["report_file"] = str(out)
    if args.output_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
