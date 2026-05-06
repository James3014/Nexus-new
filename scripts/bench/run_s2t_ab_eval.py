#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _rate(rows: list[dict[str, Any]], key: str) -> float:
    return round(sum(1 for row in rows if bool(row.get(key))) / len(rows), 4) if rows else 0.0


def _num(row: dict[str, Any], key: str) -> float:
    try:
        return float(row.get(key, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def build_s2t_eval(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [row for row in rows if bool(row.get("run_eligible", True))]
    overridden = [
        row
        for row in eligible
        if str(row.get("original_top1_candidate_id") or "") != str(row.get("s2t_selected_candidate_id") or "")
    ]
    original_verified = [row for row in eligible if bool(row.get("original_top1_verified"))]
    override_verified = [row for row in overridden if bool(row.get("s2t_selected_verified"))]
    return {
        "schema_version": "nexus_s2t_ab_eval.v1",
        "eligible_rows": len(eligible),
        "selector_override_rate": round(len(overridden) / len(eligible), 4) if eligible else 0.0,
        "selector_override_verified_rate": round(len(override_verified) / len(overridden), 4) if overridden else 0.0,
        "original_top1_verified_rate": round(len(original_verified) / len(eligible), 4) if eligible else 0.0,
        "trust_mismatch_rate": _rate(eligible, "trust_mismatch"),
        "avg_time_to_verified": round(
            sum(_num(row, "time_to_verified") for row in eligible if bool(row.get("s2t_selected_verified")))
            / max(1, sum(1 for row in eligible if bool(row.get("s2t_selected_verified")))),
            4,
        ),
        "cost_comparable_rate": _rate(eligible, "public_cost_evidence"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate S2T shadow/current rows.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    report = build_s2t_eval(_load_jsonl(args.input))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["eligible_rows"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
