#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_promotion import write_capability_skill_promotion_policy


DEFAULT_CATALOG = Path("docs/reports/NEXUS_SKILL_FIT_CATALOG_REPAIR_AND_CODING_FLASH180_2026-05-16.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_CAPABILITY_SKILL_PROMOTION_DRAFT_REPAIR_AND_CODING_FLASH180_2026-05-16.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a receipt-backed capability-skill promotion draft.")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    policy = write_capability_skill_promotion_policy(catalog_path=args.catalog, output_path=args.output)
    print(
        json.dumps(
            {
                "status": policy["status"],
                "output": args.output,
                "defaults": policy["defaults"],
                "alternates": policy["alternates"],
                "needs_more_data": policy["needs_more_data"],
                "runtime_update_allowed": policy["runtime_update_allowed"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if policy["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
