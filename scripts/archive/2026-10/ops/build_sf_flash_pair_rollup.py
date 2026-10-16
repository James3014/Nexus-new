#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_OUTPUT = Path("docs/reports/NEXUS_SF_FLASH_PAIR_LIVE_ROLLUP_2026-05-18.json")


def _capabilities_from_matrix(matrix: dict) -> list[str]:
    return sorted({str(row.get("capability") or "") for row in matrix.get("rows", []) or [] if row.get("capability")})


def build_rollup(*, matrix: dict, reports: list[dict]) -> dict:
    comparisons = []
    blockers = []
    for report in reports:
        if report.get("status") != "PASS":
            blockers.extend(str(item) for item in report.get("blockers", []) or [])
        for item in report.get("comparisons", []) or []:
            if isinstance(item, dict):
                comparisons.append(item)
    tested = {str(item.get("capability_id") or "") for item in comparisons if item.get("capability_id")}
    all_capabilities = set(_capabilities_from_matrix(matrix))
    remaining = sorted(all_capabilities - tested)
    returned = [item for item in comparisons if item.get("verdict") != "KEEP"]
    return {
        "schema": "nexus.sf_flash_pair_live_rollup.v1",
        "status": "PASS" if not blockers and not returned else "RETURN",
        "summary": {
            "capability_count": len(all_capabilities),
            "tested_capability_count": len(tested),
            "remaining_capability_count": len(remaining),
            "comparison_count": len(comparisons),
            "keep_count": sum(1 for item in comparisons if item.get("verdict") == "KEEP"),
            "return_count": len(returned),
            "public_benchmark_allowed": False,
            "runtime_update_allowed": False,
        },
        "blockers": blockers + [f"{item.get('capability_id')}:flash_pair_return" for item in returned],
        "tested_capabilities": sorted(tested),
        "remaining_capabilities": remaining,
        "comparisons": sorted(comparisons, key=lambda item: str(item.get("capability_id") or "")),
        "claim_boundary": [
            "This rollup tracks SF Flash+Nexus versus Flash+Nexus+skill live chunks.",
            "It is not a public benchmark and does not unlock runtime update by itself.",
            "Remaining capabilities must be tested before SF live closure can be claimed.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Roll up SF Flash pair live chunk reports.")
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--report", action="append", required=True)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    rollup = build_rollup(matrix=read_json(args.matrix), reports=[read_json(path) for path in args.report])
    write_json(args.output, rollup)
    print(json.dumps({"status": rollup["status"], **rollup["summary"], "output": str(args.output)}, sort_keys=True))
    return 0 if rollup["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
