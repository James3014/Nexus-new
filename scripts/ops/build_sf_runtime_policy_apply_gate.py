#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_promotion import write_skill_fit_runtime_policy_apply_gate


DEFAULT_PATCH_PLAN = Path("docs/reports/NEXUS_SF_RUNTIME_POLICY_PATCH_PLAN_V5_2026-05-18.json")
DEFAULT_PROMOTION_REVIEW = Path("docs/reports/NEXUS_SF_RUNTIME_PROMOTION_REVIEW_V5_2026-05-18.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_SF_RUNTIME_POLICY_APPLY_GATE_V5_2026-05-18.json")
DEFAULT_OVERLAY = Path("docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V5_2026-05-18.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the SF runtime policy apply gate and overlay.")
    parser.add_argument("--patch-plan", default=str(DEFAULT_PATCH_PLAN))
    parser.add_argument("--promotion-review", default=str(DEFAULT_PROMOTION_REVIEW))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--overlay-output", default=str(DEFAULT_OVERLAY))
    args = parser.parse_args(argv)

    gate = write_skill_fit_runtime_policy_apply_gate(
        patch_plan_path=args.patch_plan,
        promotion_review_path=args.promotion_review,
        output_path=args.output,
        overlay_output_path=args.overlay_output,
    )
    print(
        json.dumps(
            {
                "status": gate["status"],
                "output": args.output,
                "overlay_output": args.overlay_output,
                **gate["summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if gate["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
