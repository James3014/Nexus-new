#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_RUNTIME = Path("docs/reports/NEXUS_SF_FINAL_RUNTIME_APPLY_DECISION_2026-05-21.json")
DEFAULT_PROMOTION = Path("docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_PROMOTION_REPORT_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_M12_34_CAPABILITY_FINAL_VERDICT_2026-05-21.json")


def build_zero_trust_v2_final_rollout_completion(*, runtime_apply: dict, promotion_report: dict) -> dict:
    by_capability = {
        str(item.get("capability_id") or ""): item
        for item in promotion_report.get("candidates", []) or []
        if isinstance(item, dict)
    }
    runtime_rows = [item for item in [*(runtime_apply.get("applied_primary", []) or []), *(runtime_apply.get("kept_primary", []) or [])] if isinstance(item, dict)]
    capability_ids = sorted({str(item.get("capability_id") or "") for item in runtime_rows if item.get("capability_id")})
    capabilities = []
    for capability_id in capability_ids:
        candidate = by_capability.get(capability_id)
        if candidate and candidate.get("status") == "READY_FOR_MANUAL_APPLY":
            verdict = "V2_READY_MANUAL_APPLY_PENDING"
            rules: list[str] = []
        elif candidate:
            verdict = "STRUCTURED_BLOCKED"
            rules = list(candidate.get("failed_security_contract_rules") or [])
        else:
            verdict = "NO_V2_CANDIDATE_READY"
            rules = ["NO_V2_BEHAVIOR_CANDIDATE"]
        capabilities.append(
            {
                "capability_id": capability_id,
                "v2_verdict": verdict,
                "failed_security_contract_rules": sorted(set(rules)),
                "v1_role": "primary_or_existing_runtime_path",
            }
        )
    counts = Counter(item["v2_verdict"] for item in capabilities)
    runtime_summary = runtime_apply.get("summary") if isinstance(runtime_apply.get("summary"), dict) else {}
    v2_default_applied_count = int(runtime_summary.get("v2_default_applied_count") or 0)
    v2_unification_complete = bool(capabilities) and v2_default_applied_count == len(capabilities)
    return {
        "schema": "nexus.zero_trust_v2.m12_final_rollout_completion.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_runtime_apply": str(DEFAULT_RUNTIME),
        "source_promotion_report": str(DEFAULT_PROMOTION),
        "summary": {
            "capability_count": len(capabilities),
            "v2_ready_manual_apply_pending_count": counts.get("V2_READY_MANUAL_APPLY_PENDING", 0),
            "structured_blocked_count": counts.get("STRUCTURED_BLOCKED", 0),
            "no_v2_candidate_ready_count": counts.get("NO_V2_CANDIDATE_READY", 0),
            "v2_default_applied_count": v2_default_applied_count,
            "m12_3_complete": True,
            "v2_unification_complete": v2_unification_complete,
            "runtime_mutation_allowed": v2_unification_complete,
            "public_benchmark_allowed": False,
        },
        "capabilities": capabilities,
        "claim_boundary": [
            "M12-3 completion means every capability has a V2 verdict, not that every capability is V2 promoted.",
            "Runtime unification remains blocked until capabilities have V2 behavior evidence.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 M12 34-capability final verdict.")
    parser.add_argument("--runtime-apply", default=str(DEFAULT_RUNTIME))
    parser.add_argument("--promotion-report", default=str(DEFAULT_PROMOTION))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_zero_trust_v2_final_rollout_completion(
        runtime_apply=read_json(args.runtime_apply),
        promotion_report=read_json(args.promotion_report),
    )
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
