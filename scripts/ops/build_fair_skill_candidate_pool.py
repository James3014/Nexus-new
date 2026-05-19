#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.fair_skill_candidate_pool import write_fair_skill_candidate_pool


DEFAULT_STATUS_REPORT = Path("docs/reports/NEXUS_SKILL_STATUS_2026-05-15.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_FAIR_SKILL_CANDIDATE_POOL_2026-05-15.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a source-neutral skill candidate pool for ablation.")
    parser.add_argument("--status-report", default=str(DEFAULT_STATUS_REPORT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    pool = write_fair_skill_candidate_pool(status_report_path=args.status_report, output_path=args.output)
    print(
        json.dumps(
            {
                "status": pool["status"],
                "output": args.output,
                **pool["summary"],
                "violation_count": len(pool["violations"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if pool["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
