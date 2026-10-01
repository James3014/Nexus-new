#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nexus.research.core_effectiveness_observability import (  # noqa: E402
    build_g0_coverage_report,
)


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            value = json.loads(stripped)
            if not isinstance(value, dict):
                raise ValueError(f"line {line_number}: observation must be a JSON object")
            rows.append(value)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure Nexus Core effectiveness G0 prospective enrollment coverage."
    )
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--target", type=float, default=0.95)
    args = parser.parse_args()

    report = build_g0_coverage_report(
        _read_jsonl(args.observations),
        target=args.target,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report["gate"] == "G0_COVERAGE_TARGET_MET" else 2


if __name__ == "__main__":
    raise SystemExit(main())
