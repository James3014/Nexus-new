#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_promotion import write_skill_fit_runtime_promotion_review


DEFAULT_CATALOG = Path("docs/reports/NEXUS_SF_FINAL_CAPABILITY_SKILL_CATALOG_2026-05-18.json")
DEFAULT_PROMOTION_POLICY = Path("docs/reports/NEXUS_SF_CAPABILITY_SKILL_PROMOTION_POLICY_DRAFT_2026-05-18.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_SF_RUNTIME_PROMOTION_REVIEW_2026-05-18.json")
DEFAULT_CANDIDATE_SOURCES = (
    Path("docs/reports/NEXUS_FAIR_SKILL_CANDIDATE_POOL_2026-05-17_SF_REFRESH.json"),
    Path("docs/reports/NEXUS_SF_GOVERNANCE_CANDIDATE_POOL_V3_2026-05-18.json"),
    Path("docs/reports/NEXUS_SF_RESEARCH_MATERIALIZED_SKILL_ASSETS_2026-05-18.json"),
    Path("docs/reports/NEXUS_SKILL_STATUS_SF_RESEARCH_2026-05-18.json"),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the SF runtime-promotion review disposition report.")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--promotion-policy", default=str(DEFAULT_PROMOTION_POLICY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--candidate-source",
        action="append",
        default=[str(path) for path in DEFAULT_CANDIDATE_SOURCES],
        help="JSON candidate/status source. May be repeated.",
    )
    args = parser.parse_args(argv)

    review = write_skill_fit_runtime_promotion_review(
        catalog_path=args.catalog,
        promotion_policy_path=args.promotion_policy,
        output_path=args.output,
        candidate_source_paths=args.candidate_source,
    )
    print(
        json.dumps(
            {
                "status": review["status"],
                "output": args.output,
                "sf_closed_loop_complete": review["sf_closed_loop_complete"],
                "runtime_update_allowed": review["runtime_update_allowed"],
                "public_benchmark_allowed": review["public_benchmark_allowed"],
                **review["summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if review["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
