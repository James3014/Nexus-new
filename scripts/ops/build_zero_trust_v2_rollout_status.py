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


DEFAULT_RUNTIME = Path("docs/reports/NEXUS_SF_FINAL_RUNTIME_APPLY_DECISION_2026-05-21.json")
DEFAULT_UNIFICATION = Path("docs/reports/NEXUS_ZERO_TRUST_V2_UNIFICATION_PLAN_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_34_CAPABILITY_ROLLOUT_STATUS_2026-05-21.json")


def build_zero_trust_v2_rollout_status(*, runtime_apply: dict, unification_plan: dict) -> dict:
    applied = runtime_apply.get("applied_primary", []) or []
    kept = runtime_apply.get("kept_primary", []) or []
    ready_by_capability = {
        item["capability_id"]: item
        for item in unification_plan.get("patch_plan", []) or []
        if isinstance(item, dict)
    }
    capability_ids = sorted({str(item.get("capability_id") or "") for item in [*applied, *kept] if isinstance(item, dict) and item.get("capability_id")})
    capabilities = []
    for capability_id in capability_ids:
        capabilities.append(
            {
                "capability_id": capability_id,
                "v2_default_ready": capability_id in ready_by_capability,
                "runtime_primary_source": "v2_ready_manual_apply_pending" if capability_id in ready_by_capability else "v1_overlay_or_existing_primary",
                "v1_role": "fallback_pending_operator_ack" if capability_id in ready_by_capability else "primary_or_existing_runtime_path",
            }
        )
    v2_ready_count = sum(1 for item in capabilities if item["v2_default_ready"])
    return {
        "schema": "nexus.zero_trust_v2.rollout_status.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_runtime_apply": str(DEFAULT_RUNTIME),
        "source_unification_plan": str(DEFAULT_UNIFICATION),
        "summary": {
            "capability_count": len(capabilities),
            "v2_default_ready_count": v2_ready_count,
            "v1_primary_or_existing_count": len(capabilities) - v2_ready_count,
            "unification_complete": v2_ready_count == len(capabilities) and bool(capabilities),
            "runtime_mutation_allowed": False,
            "public_benchmark_allowed": False,
        },
        "capabilities": capabilities,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 34-capability rollout status.")
    parser.add_argument("--runtime-apply", default=str(DEFAULT_RUNTIME))
    parser.add_argument("--unification-plan", default=str(DEFAULT_UNIFICATION))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_zero_trust_v2_rollout_status(
        runtime_apply=read_json(args.runtime_apply),
        unification_plan=read_json(args.unification_plan),
    )
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
