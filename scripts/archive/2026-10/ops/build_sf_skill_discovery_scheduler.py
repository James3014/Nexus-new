#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_discovery_lane import write_capability_skill_discovery_scheduler


DEFAULT_CANDIDATE_POOL = Path("docs/reports/NEXUS_FAIR_SKILL_CANDIDATE_POOL_2026-05-17_SF_REFRESH.json")
DEFAULT_CATALOG = Path("docs/reports/NEXUS_SF_FINAL_CAPABILITY_SKILL_CATALOG_V5_2026-05-18.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_SF_CAPABILITY_SKILL_DISCOVERY_SCHEDULER_2026-05-18.json")


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the SF capability-skill discovery scheduler queue.")
    parser.add_argument("--candidate-pool", default=str(DEFAULT_CANDIDATE_POOL))
    parser.add_argument("--current-catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--refresh-plan", default="")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--capabilities", default="")
    parser.add_argument("--max-skill-arms", type=int, default=4)
    args = parser.parse_args(argv)

    scheduler = write_capability_skill_discovery_scheduler(
        candidate_pool_path=args.candidate_pool,
        current_catalog_path=args.current_catalog,
        refresh_plan_path=args.refresh_plan or None,
        output_path=args.output,
        capabilities=_csv(args.capabilities),
        max_skill_arms=args.max_skill_arms,
    )
    print(
        json.dumps(
            {
                "status": scheduler["status"],
                "output": args.output,
                "runtime_update_allowed": scheduler["runtime_update_allowed"],
                "public_benchmark_allowed": scheduler["public_benchmark_allowed"],
                **scheduler["summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if scheduler["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
