#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json
from nexus.learning.zero_trust_v2_receipts import verify_runtime_signed_receipt


DEFAULT_M36_M44 = Path("docs/reports/NEXUS_ZERO_TRUST_V2_M36_M44_COMPLETION_2026-05-21.json")
DEFAULT_RUNNER_MATRIX = Path("docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_RUNNER_MATRIX_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_M45_M52_COMPLETION_2026-05-22.json")
DEFAULT_SIGNING_SECRET_PATH = Path(".nexus/reports/zero_trust_v2_behavior/.runtime_signing_secret")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _flatten_strings(values: list[Any]) -> list[str]:
    return [str(value) for value in values if str(value)]


def _read_bundle(path: str) -> dict[str, Any] | None:
    bundle_path = Path(path)
    if not path or not bundle_path.exists():
        return None
    return read_json(bundle_path)


def _load_signing_secret() -> str:
    import os

    env_secret = os.environ.get("NEXUS_ZERO_TRUST_V2_RECEIPT_SIGNING_SECRET", "").strip()
    if env_secret:
        return env_secret
    if DEFAULT_SIGNING_SECRET_PATH.exists():
        return DEFAULT_SIGNING_SECRET_PATH.read_text(encoding="utf-8").strip()
    return ""


def _find_runtime_signed_receipt(bundle: dict[str, Any]) -> dict[str, Any] | None:
    if bundle.get("receipt_provenance") == "runtime_signed":
        return bundle
    stack = [bundle]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if current.get("receipt_provenance") == "runtime_signed":
                return current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return None


def _runtime_signed_receipt_status(bundle: dict[str, Any]) -> tuple[bool, bool]:
    receipt = _find_runtime_signed_receipt(bundle)
    if receipt is None:
        return False, False
    secret = _load_signing_secret()
    if not secret:
        return True, False
    return True, verify_runtime_signed_receipt(receipt, secret=secret)


def _slug_path(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in value).strip("-") or "unknown"


def _full_matrix_run_plan(runner_matrix: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for adapter in _as_list(runner_matrix.get("adapters")):
        if not isinstance(adapter, dict) or adapter.get("status") != "READY_FOR_PHYSICAL_BEHAVIOR_RUN":
            continue
        cap = str(adapter.get("capability_id") or "")
        skill = str(adapter.get("skill_id") or "")
        priority = str(adapter.get("priority") or "")
        for index in range(1, 4):
            output_dir = f".nexus/reports/zero_trust_v2_behavior/{_slug_path(cap)}/{_slug_path(skill)}/run-{index:02d}"
            rows.append(
                {
                    "run_id": f"ztv2-matrix-{cap}-{skill}-{index:02d}",
                    "run_index": index,
                    "capability_id": cap,
                    "skill_id": skill,
                    "priority": priority,
                    "expected_evidence_bundle": f"{output_dir}/evidence_bundle.json",
                }
            )
    return rows


def _summarize_run(item: dict[str, Any]) -> dict[str, Any]:
    bundle_path = str(item.get("expected_evidence_bundle") or "")
    bundle = _read_bundle(bundle_path)
    if bundle is None:
        return {
            "run_id": str(item.get("run_id") or ""),
            "run_index": int(item.get("run_index") or 0),
            "capability_id": str(item.get("capability_id") or ""),
            "skill_id": str(item.get("skill_id") or ""),
            "priority": str(item.get("priority") or ""),
            "evidence_bundle": bundle_path,
            "status": "NOT_EXECUTED",
            "clean_v2_receipt": False,
            "blockers": ["missing_evidence_bundle"],
        }
    with_summary = _as_dict(_as_dict(bundle.get("benchmark_summary")).get("with_nexus"))
    row_counts = _as_dict(bundle.get("row_counts"))
    rubric = _as_dict(_as_dict(bundle.get("rubric_contract")).get("with_nexus"))
    hard_failures = _flatten_strings(_as_list(rubric.get("hard_fail_reasons")))
    infra_reasons = _flatten_strings(_as_list(with_summary.get("infra_invalid_reasons")))
    runtime_signed, runtime_signature_verified = _runtime_signed_receipt_status(bundle)
    eligible_rows = int(row_counts.get("eligible_with_nexus") or 0)
    blockers = sorted(set([*hard_failures, *infra_reasons]))
    if not runtime_signed:
        blockers.append("missing_runtime_signed_v2_receipt")
    elif not runtime_signature_verified:
        blockers.append("runtime_signed_v2_receipt_signature_unverified")
    if eligible_rows <= 0:
        blockers.append("no_eligible_behavior_row")
    clean = runtime_signed and runtime_signature_verified and eligible_rows > 0 and not blockers

    return {
        "run_id": str(item.get("run_id") or ""),
        "run_index": int(item.get("run_index") or 0),
        "capability_id": str(item.get("capability_id") or ""),
        "skill_id": str(item.get("skill_id") or ""),
        "priority": str(item.get("priority") or ""),
        "evidence_bundle": bundle_path,
        "status": "CLEAN_V2_RECEIPT" if clean else "EXECUTED_BUT_BLOCKED",
        "clean_v2_receipt": clean,
        "runtime_signed_receipt_present": runtime_signed,
        "runtime_signed_receipt_verified": runtime_signature_verified,
        "eligible_behavior_rows": eligible_rows,
        "infra_invalid_reasons": infra_reasons,
        "hard_fail_reasons": hard_failures,
        "blockers": sorted(set(blockers)),
    }


def build_zero_trust_v2_m45_m52_completion(*, m36_m44: dict[str, Any], runner_matrix: dict[str, Any] | None = None) -> dict[str, Any]:
    matrix_plan = _full_matrix_run_plan(runner_matrix or {}) if runner_matrix else []
    run_plan = matrix_plan or [
        item
        for item in _as_list(_as_dict(m36_m44.get("m38_signed_behavior_execution_gate")).get("run_plan"))
        if isinstance(item, dict)
    ]
    run_results = [_summarize_run(item) for item in run_plan]
    status_counts = Counter(item["status"] for item in run_results)
    blocker_counts = Counter(blocker for item in run_results for blocker in item.get("blockers", []))
    executed_count = sum(1 for item in run_results if item["status"] != "NOT_EXECUTED")
    clean_count = sum(1 for item in run_results if item.get("clean_v2_receipt") is True)
    required_clean_count = len(run_plan) if matrix_plan else 3
    ready_for_manual_apply = clean_count >= required_clean_count and required_clean_count > 0 and not blocker_counts

    selected = _as_dict(m36_m44.get("selected_canary_candidate"))
    p0_ready = int(_as_dict(m36_m44.get("summary")).get("m42_p0_ready_for_execution_count") or 0)
    p1_p2_ready = int(_as_dict(m36_m44.get("summary")).get("m43_p1_p2_ready_for_execution_count") or 0)
    if matrix_plan:
        m45_status = "PASS" if clean_count >= required_clean_count else "PARTIAL_MATRIX_BLOCKED"
    else:
        m45_status = "BLOCKED_AFTER_FIRST_RUN" if executed_count and clean_count < 3 else ("PASS" if clean_count >= 3 else "NOT_EXECUTED")
    ready_capabilities = {
        str(item.get("capability_id") or "")
        for item in run_results
        if item.get("capability_id") and item.get("clean_v2_receipt") is True
    }
    if matrix_plan:
        ready_capabilities = {
            capability
            for capability in ready_capabilities
            if sum(
                1
                for item in run_results
                if item.get("capability_id") == capability and item.get("clean_v2_receipt") is True
            )
            >= 3
        }
        ready_priority_by_capability = {
            str(item.get("capability_id") or ""): str(item.get("priority") or "")
            for item in run_results
            if item.get("capability_id") in ready_capabilities
        }
        p0_ready = sum(1 for priority in ready_priority_by_capability.values() if priority == "P0")
        p1_p2_ready = sum(1 for priority in ready_priority_by_capability.values() if priority in {"P1", "P2"})
    ready_capability_count = len(ready_capabilities)
    remaining_capability_count = max(0, 34 - ready_capability_count)
    full_coverage_ready = ready_capability_count >= 34

    return {
        "schema": "nexus.zero_trust_v2.m45_m52_completion.v1",
        "status": "BLOCKED" if not ready_for_manual_apply else "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_m36_m44": str(DEFAULT_M36_M44),
        "summary": {
            "m45_behavior_run_plan_count": len(run_plan),
            "m45_behavior_run_executed_count": executed_count,
            "m45_clean_v2_receipt_count": clean_count,
            "m45_status": m45_status,
            "m46_receipt_import_ready": ready_for_manual_apply,
            "m46_receipt_imported_count": clean_count if ready_for_manual_apply else 0,
            "m47_manual_apply_trial_ready": False,
            "m48_canary_apply_ready": False,
            "m49_p0_ready_for_execution_count": p0_ready,
            "m49_p0_promoted_count": 0,
            "m50_p1_p2_ready_for_execution_count": p1_p2_ready,
            "m50_p1_p2_promoted_count": 0,
            "m51_v2_ready_capability_count": len(ready_capabilities),
            "m52_v1_path_closure_ready": full_coverage_ready,
            "v2_unification_complete": False,
            "runtime_mutation_allowed": False,
            "automatic_apply_allowed": False,
            "public_benchmark_allowed": False,
            "promotion_credit_allowed": False,
        },
        "selected_canary_candidate": selected,
        "m45_behavior_run_results": run_results,
        "m46_receipt_import_gate": {
            "status": "PASS" if ready_for_manual_apply else "BLOCKED",
            "required_clean_v2_receipt_count": required_clean_count,
            "clean_v2_receipt_count": clean_count,
            "dominant_blockers": [{"reason": reason, "count": count} for reason, count in blocker_counts.most_common()],
        },
        "m47_manual_apply_trial_gate": {
            "status": "BLOCKED",
            "blockers": [] if ready_for_manual_apply else ["receipt_import_gate_not_passed"],
            "operator_ack_required": True,
        },
        "m48_canary_apply_rollback_gate": {
            "status": "BLOCKED",
            "blockers": ["manual_apply_trial_not_ready"],
            "post_apply_smoke_required": True,
            "rollback_proof_required": True,
        },
        "m49_p0_rollout_gate": {
            "status": "BLOCKED",
            "ready_for_execution_count": p0_ready,
            "promoted_count": 0,
            "blockers": ["canary_receipt_import_not_clean"],
        },
        "m50_p1_p2_rollout_gate": {
            "status": "BLOCKED",
            "ready_for_execution_count": p1_p2_ready,
            "promoted_count": 0,
            "blockers": ["p0_rollout_not_complete"],
        },
        "m51_34_capability_gap": {
            "status": "PASS" if full_coverage_ready else "BLOCKED",
            "v2_ready_capability_count": ready_capability_count,
            "required_v2_ready_capability_count": 34,
            "remaining_capability_count": remaining_capability_count,
        },
        "m52_v1_path_closure_gate": {
            "status": "PASS" if full_coverage_ready else "BLOCKED",
            "blockers": [] if full_coverage_ready else ["34_capability_v2_ready_not_met"],
            "closure_apply_plan_allowed": full_coverage_ready,
        },
        "required_next_hooks": [
            {
                "hook": "expected_capability_receipt_bridge",
                "purpose": "Convert invoked expected capability evidence into public-safe gate-passed receipts before V2 import.",
                "required_for": "receipt_data_contract_violation",
            },
            {
                "hook": "runtime_signed_behavior_receipt_export",
                "purpose": "Write runtime_signed V2 receipt metadata into the behavior evidence bundle rather than relying on benchmark rows alone.",
                "required_for": "missing_runtime_signed_v2_receipt",
            },
            {
                "hook": "provider_token_measurement_or_cost_claim_off",
                "purpose": "Keep public/cost/training claims off unless provider token telemetry is measured.",
                "required_for": "token_telemetry_incomplete",
            },
        ],
        "claim_boundary": [
            "M45 attempted one real canary run and stopped after a fail-closed evidence contract violation.",
            "M46-M52 are intentionally blocked until clean runtime-signed V2 behavior receipts exist.",
            "V2 cannot be unified by report synthesis; it requires clean behavior receipts plus manual apply and rollback gates.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 M45-M52 completion report.")
    parser.add_argument("--m36-m44", default=str(DEFAULT_M36_M44))
    parser.add_argument("--runner-matrix", default="")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    runner_matrix = read_json(args.runner_matrix) if args.runner_matrix else None
    result = build_zero_trust_v2_m45_m52_completion(m36_m44=read_json(args.m36_m44), runner_matrix=runner_matrix)
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
