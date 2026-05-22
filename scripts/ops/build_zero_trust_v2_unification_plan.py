#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_ACCUMULATION = Path("docs/reports/NEXUS_ZERO_TRUST_V2_EVIDENCE_ACCUMULATION_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_UNIFICATION_PLAN_2026-05-21.json")


def build_zero_trust_v2_unification_plan(*, accumulation: dict) -> dict:
    ready = [item for item in accumulation.get("candidates", []) or [] if isinstance(item, dict) and item.get("status") == "READY_FOR_MANUAL_APPLY"]
    patch_plan = [
        {
            "capability_id": item["capability_id"],
            "skill_id": item["skill_id"],
            "action": "promote_v2_primary_keep_v1_fallback",
            "requires_operator_ack": True,
            "requires_revert_plan": True,
        }
        for item in ready
    ]
    return {
        "schema": "nexus.zero_trust_v2.unification_plan.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_accumulation": str(DEFAULT_ACCUMULATION),
        "summary": {
            "ready_for_manual_apply_count": len(ready),
            "patch_plan_count": len(patch_plan),
            "v1_role_after_apply": "fallback_only" if patch_plan else "runtime_overlay_primary_until_v2_ready",
            "runtime_mutation_allowed": False,
            "automatic_apply_allowed": False,
            "public_benchmark_allowed": False,
        },
        "patch_plan": patch_plan,
        "blockers": [] if patch_plan else ["no_v2_ready_candidates"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 unification plan.")
    parser.add_argument("--accumulation", default=str(DEFAULT_ACCUMULATION))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_zero_trust_v2_unification_plan(accumulation=read_json(args.accumulation))
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
