#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_promotion import write_skill_fit_completion_gate


DEFAULT_CATALOG = Path("docs/reports/NEXUS_SF_FINAL_CAPABILITY_SKILL_CATALOG_2026-05-18.json")
DEFAULT_PROMOTION_POLICY = Path("docs/reports/NEXUS_SF_CAPABILITY_SKILL_PROMOTION_POLICY_DRAFT_2026-05-18.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_SF_COMPLETION_GATE_2026-05-18.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the non-runtime SF completion gate.")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--promotion-policy", default=str(DEFAULT_PROMOTION_POLICY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    gate = write_skill_fit_completion_gate(
        catalog_path=args.catalog,
        promotion_policy_path=args.promotion_policy,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "status": gate["status"],
                "output": args.output,
                "skill_fit_complete": gate["skill_fit_complete"],
                "sf_runtime_promotion_complete": gate["sf_runtime_promotion_complete"],
                "runtime_update_allowed": gate["runtime_update_allowed"],
                "public_benchmark_allowed": gate["public_benchmark_allowed"],
                **gate["summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if gate["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
