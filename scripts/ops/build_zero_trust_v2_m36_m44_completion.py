#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_M28_M35 = Path("docs/reports/NEXUS_ZERO_TRUST_V2_M28_M35_EXECUTION_PLAN_2026-05-21.json")
DEFAULT_PREFLIGHT = Path(".nexus/reports/zero_trust_v2_behavior/policy_capability_gate/browse/preflight/benchmark_preflight.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_M36_M44_COMPLETION_2026-05-21.json")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _gate_status(blockers: list[str]) -> str:
    return "PASS" if not blockers else "BLOCKED"


def _existing_receipt_bundles(run_plan: list[dict[str, Any]]) -> list[str]:
    bundles: list[str] = []
    for item in run_plan:
        bundle = str(item.get("expected_evidence_bundle") or "")
        if bundle and Path(bundle).exists():
            bundles.append(bundle)
    return bundles


def build_zero_trust_v2_m36_m44_completion(*, m28_m35: dict[str, Any], preflight: dict[str, Any] | None) -> dict[str, Any]:
    preflight = preflight or {}
    preflight_failures = [str(item) for item in _as_list(preflight.get("failures"))]
    preflight_warnings = [str(item) for item in _as_list(preflight.get("warnings"))]
    preflight_status = str(preflight.get("status") or "MISSING")
    preflight_passed = preflight_status == "PASS" and not preflight_failures

    run_plan = [
        item
        for item in _as_list(m28_m35.get("m29_three_run_plan"))
        if isinstance(item, dict) and item.get("command")
    ]
    receipt_bundles = _existing_receipt_bundles(run_plan)
    required_receipts = 3 if run_plan else 0
    clean_v2_receipts = 0

    m38_blockers = [] if preflight_passed else ["m36_preflight_not_passed"]
    m39_blockers = []
    if not preflight_passed:
        m39_blockers.append("m36_preflight_not_passed")
    if len(receipt_bundles) < required_receipts:
        m39_blockers.append("missing_signed_v2_behavior_receipts")
    if clean_v2_receipts < required_receipts:
        m39_blockers.append("clean_v2_receipt_threshold_not_met")

    m40_blockers = [] if not m39_blockers else ["receipt_import_gate_not_passed"]
    m41_blockers = [] if not m40_blockers else ["manual_apply_trial_not_ready"]

    summary = m28_m35.get("summary", {}) if isinstance(m28_m35.get("summary"), dict) else {}
    p0_ready_for_execution = int(summary.get("m33_p0_ready_for_execution_count") or 0)
    p1_p2_ready_for_execution = int(summary.get("m34_p1_p2_ready_for_execution_count") or 0)
    v2_ready_capabilities = 0

    return {
        "schema": "nexus.zero_trust_v2.m36_m44_completion.v1",
        "status": "PASS" if preflight_passed else "BLOCKED",
        "created_at": datetime.now(UTC).isoformat(),
        "source_m28_m35": str(DEFAULT_M28_M35),
        "source_preflight": str(DEFAULT_PREFLIGHT),
        "summary": {
            "m36_preflight_status": preflight_status,
            "m36_preflight_failure_count": len(preflight_failures),
            "m36_preflight_warning_count": len(preflight_warnings),
            "m37_blocker_repair_complete": preflight_passed,
            "m38_signed_behavior_run_plan_count": len(run_plan),
            "m38_signed_behavior_run_executed_count": len(receipt_bundles),
            "m39_existing_receipt_bundle_count": len(receipt_bundles),
            "m39_clean_v2_receipt_count": clean_v2_receipts,
            "m40_manual_apply_trial_ready_count": 0,
            "m41_canary_apply_ready": False,
            "m42_p0_ready_for_execution_count": p0_ready_for_execution,
            "m42_p0_promoted_count": 0,
            "m43_p1_p2_ready_for_execution_count": p1_p2_ready_for_execution,
            "m43_p1_p2_promoted_count": 0,
            "m44_v2_ready_capability_count": v2_ready_capabilities,
            "m44_v1_path_closure_ready": False,
            "v2_unification_complete": False,
            "runtime_mutation_allowed": False,
            "automatic_apply_allowed": False,
            "public_benchmark_allowed": False,
            "promotion_credit_allowed": False,
        },
        "selected_canary_candidate": m28_m35.get("selected_canary_candidate") if isinstance(m28_m35.get("selected_canary_candidate"), dict) else {},
        "m36_preflight_result": {
            "status": preflight_status,
            "failures": preflight_failures,
            "warnings": preflight_warnings,
            "report_path": str(DEFAULT_PREFLIGHT),
            "claim_boundary": "Preflight proves runner/task wiring only; it is not signed V2 behavior evidence.",
        },
        "m37_blocker_repair_gate": {
            "status": _gate_status([] if preflight_passed else ["preflight_failures_present"]),
            "repairs_recorded": [
                "adapter uses --gemini-model instead of unsupported --model",
                "fresh task rows omit private zero_trust_v2 metadata",
                "non-core V2 capability ids are mapped to runner-core expected capabilities",
            ],
            "blockers": [] if preflight_passed else preflight_failures or ["preflight_missing_or_failed"],
        },
        "m38_signed_behavior_execution_gate": {
            "status": "READY_TO_RUN" if not m38_blockers and run_plan else _gate_status(m38_blockers or ["missing_behavior_run_plan"]),
            "run_plan": run_plan,
            "executed_receipt_bundles": receipt_bundles,
            "blockers": m38_blockers,
            "promotion_credit_allowed": False,
        },
        "m39_receipt_import_gate": {
            "status": _gate_status(m39_blockers),
            "required_signed_receipt_count": required_receipts,
            "existing_receipt_bundle_count": len(receipt_bundles),
            "clean_v2_receipt_count": clean_v2_receipts,
            "trust_mismatch_count": 0,
            "blockers": m39_blockers,
        },
        "m40_manual_apply_trial_gate": {
            "status": _gate_status(m40_blockers),
            "operator_ack_required": True,
            "blockers": m40_blockers,
        },
        "m41_canary_apply_rollback_gate": {
            "status": _gate_status(m41_blockers),
            "post_apply_smoke_required": True,
            "rollback_proof_required": True,
            "blockers": m41_blockers,
        },
        "m42_p0_rollout_gate": {
            "status": "BLOCKED",
            "ready_for_execution_count": p0_ready_for_execution,
            "promoted_count": 0,
            "blockers": ["canary_apply_rollback_gate_not_passed"],
        },
        "m43_p1_p2_rollout_gate": {
            "status": "BLOCKED",
            "ready_for_execution_count": p1_p2_ready_for_execution,
            "promoted_count": 0,
            "blockers": ["p0_rollout_not_complete"],
        },
        "m44_v1_path_closure_gate": {
            "status": "BLOCKED",
            "v2_ready_capability_count": v2_ready_capabilities,
            "required_v2_ready_capability_count": 34,
            "blockers": ["v2_unification_incomplete"],
        },
        "claim_boundary": [
            "M36 preflight can pass while M38-M44 remain blocked.",
            "Only runtime-signed clean V2 behavior receipts may feed manual apply readiness.",
            "V1 promotion path remains open until all 34 capabilities are V2 ready.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 M36-M44 completion report.")
    parser.add_argument("--m28-m35", default=str(DEFAULT_M28_M35))
    parser.add_argument("--preflight", default=str(DEFAULT_PREFLIGHT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    preflight = read_json(args.preflight) if Path(args.preflight).exists() else None
    result = build_zero_trust_v2_m36_m44_completion(
        m28_m35=read_json(args.m28_m35),
        preflight=preflight,
    )
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
