#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import build_sf_flash_pair_live_report, read_json, write_json


DEFAULT_OUTPUT = Path("docs/reports/NEXUS_SF_FLASH_PAIR_LIVE_REPORT_2026-05-18.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build SF Flash+Nexus vs Flash+Nexus+skill live report.")
    parser.add_argument("--live-summary", required=True)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report = build_sf_flash_pair_live_report(live_summary=read_json(args.live_summary))
    write_json(args.output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                **report["summary"],
                "output": str(args.output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
