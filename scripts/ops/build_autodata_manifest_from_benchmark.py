#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from nexus.engine.autodata_forge import (
    benchmark_rows_to_data_forge_rows,
    validate_hard_trajectory_pool,
    write_data_forge_manifest,
)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"invalid benchmark row {line_number}: expected object")
        rows.append(row)
    return rows


def build_autodata_manifest_from_benchmark(
    *,
    with_nexus: Path,
    without_nexus: Path,
    output: Path,
    min_rows: int = 2,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not with_nexus.exists():
        raise ValueError(f"with_nexus_missing:{with_nexus}")
    if not without_nexus.exists():
        raise ValueError(f"without_nexus_missing:{without_nexus}")

    rows = benchmark_rows_to_data_forge_rows(
        strong_rows=_load_jsonl(with_nexus),
        weak_rows=_load_jsonl(without_nexus),
        strong_source=str(with_nexus),
        weak_source=str(without_nexus),
    )
    validation = validate_hard_trajectory_pool(rows, min_rows=min_rows)
    write_summary = None if dry_run else write_data_forge_manifest(output, rows)
    payload_rows = [row.to_dict() for row in rows]
    return {
        "schema_version": "nexus_autodata_benchmark_export.v1",
        "passed": bool(validation["passed"]),
        "dry_run": bool(dry_run),
        "with_nexus": str(with_nexus),
        "without_nexus": str(without_nexus),
        "output": str(output),
        "row_count": len(rows),
        "gold_count": sum(1 for row in payload_rows if row["label"]["label"] == "GOLD"),
        "training_eligible_count": sum(1 for row in payload_rows if row["eligible_for_training"]),
        "hard_negative_count": sum(1 for row in payload_rows if row["hard_negative"]),
        "low_step_filtered_count": sum(1 for row in payload_rows if row["low_step_filter"]["filtered"]),
        "validation": validation,
        "write_summary": write_summary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Nexus Autodata manifest from same-model benchmark rows.")
    parser.add_argument("--with-nexus", required=True, type=Path)
    parser.add_argument("--without-nexus", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--min-rows", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        summary = build_autodata_manifest_from_benchmark(
            with_nexus=args.with_nexus,
            without_nexus=args.without_nexus,
            output=args.output,
            min_rows=args.min_rows,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001 - command boundary returns structured failure.
        summary = {
            "schema_version": "nexus_autodata_benchmark_export.v1",
            "passed": False,
            "error": str(exc),
            "with_nexus": str(args.with_nexus),
            "without_nexus": str(args.without_nexus),
            "output": str(args.output),
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
