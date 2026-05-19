#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_status import write_skill_fit_status_rollup


DEFAULT_PROMOTION_POLICIES = (
    "docs/reports/NEXUS_CAPABILITY_SKILL_PROMOTION_DRAFT_REPAIR_AND_CODING_SF_TDD_SEAL_2026-05-17.json",
    "docs/reports/NEXUS_CAPABILITY_SKILL_PROMOTION_DRAFT_GOVERNANCE_AND_TRUST_V2C_FLASH30_LIVE_2026-05-17.json",
    "docs/reports/NEXUS_CAPABILITY_SKILL_PROMOTION_DRAFT_RESEARCH_AND_SOURCE_DISCIPLINE_V2_FULL_LIVE_2026-05-17.json",
)
DEFAULT_THRESHOLD_CONTRACTS = (
    "docs/reports/NEXUS_SKILL_PROMOTION_THRESHOLD_CONTRACT_REPAIR_AND_CODING_SF_TDD_SEAL_2026-05-17.json",
    "docs/reports/NEXUS_SKILL_PROMOTION_THRESHOLD_CONTRACT_GOVERNANCE_AND_TRUST_V2C_FLASH30_LIVE_2026-05-17.json",
    "docs/reports/NEXUS_SKILL_PROMOTION_THRESHOLD_CONTRACT_RESEARCH_AND_SOURCE_DISCIPLINE_V2_FULL_LIVE_2026-05-17.json",
)
DEFAULT_OUTPUT = "docs/reports/NEXUS_SF_CAPABILITY_SKILL_STATUS_ROLLUP_2026-05-17.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build skill-fit status rollup without running benchmarks.")
    parser.add_argument("--promotion-policy", action="append", default=list(DEFAULT_PROMOTION_POLICIES))
    parser.add_argument("--threshold-contract", action="append", default=list(DEFAULT_THRESHOLD_CONTRACTS))
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    rollup = write_skill_fit_status_rollup(
        promotion_policy_paths=args.promotion_policy,
        threshold_contract_paths=args.threshold_contract,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "status": rollup["status"],
                "output": args.output,
                "has_found_skill": rollup["has_found_skill"],
                "promotion_ready": rollup["promotion_ready"],
                "benchmark_allowed": rollup["benchmark_allowed"],
                **rollup["summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if rollup["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
