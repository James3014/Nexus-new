#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_promotion import write_skill_promotion_threshold_contract


DEFAULT_CATALOG = Path("docs/reports/NEXUS_SKILL_FIT_CATALOG_REPAIR_AND_CODING_FLASH180_2026-05-16.json")
DEFAULT_PROMOTION = Path("docs/reports/NEXUS_CAPABILITY_SKILL_PROMOTION_DRAFT_REPAIR_AND_CODING_FLASH180_2026-05-16.json")
DEFAULT_QUEUE = Path("docs/reports/NEXUS_SKILL_DISCOVERY_RERUN_QUEUE_REPAIR_AND_CODING_FLASH180_2026-05-16.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_SKILL_PROMOTION_THRESHOLD_CONTRACT_REPAIR_AND_CODING_FLASH180_2026-05-16.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a fail-closed skill promotion threshold contract.")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--promotion-policy", default=str(DEFAULT_PROMOTION))
    parser.add_argument("--rerun-queue", default=str(DEFAULT_QUEUE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--min-tested-rows-per-skill", type=int, default=30)
    parser.add_argument("--default-min-effective-rate", type=float, default=0.8)
    parser.add_argument("--alternate-min-effective-rate", type=float, default=0.6)
    parser.add_argument("--min-task-buckets-for-alternate", type=int, default=2)
    args = parser.parse_args(argv)

    contract = write_skill_promotion_threshold_contract(
        catalog_path=args.catalog,
        promotion_policy_path=args.promotion_policy,
        rerun_queue_path=args.rerun_queue,
        output_path=args.output,
        min_tested_rows_per_skill=args.min_tested_rows_per_skill,
        default_min_effective_rate=args.default_min_effective_rate,
        alternate_min_effective_rate=args.alternate_min_effective_rate,
        min_task_buckets_for_alternate=args.min_task_buckets_for_alternate,
    )
    print(
        json.dumps(
            {
                "status": contract["status"],
                "output": args.output,
                "flash100_allowed": contract["flash100_allowed"],
                "promotion_allowed": contract["promotion_allowed"],
                **contract["summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if contract["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
