#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_LIVE_SUMMARY = Path(".nexus/reports/sf_final_live_compare_2026-05-21/live_summary.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_SF_FINAL_LIVE_COMPARE_REPORT_2026-05-21.json")


def _bench(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("benchmark_row")
    return value if isinstance(value, Mapping) else {}


def _gate(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("ablation_gate_row")
    return value if isinstance(value, Mapping) else {}


def _number(row: Mapping[str, Any], key: str) -> float | int | None:
    value = row.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _receipt_chain_pass(row: Mapping[str, Any]) -> bool:
    gate = _gate(row)
    return all(bool(gate.get(key)) for key in ("selected", "injected", "used", "evidence_present", "gate_passed", "outcome_contributed"))


def _row_metrics(row: Mapping[str, Any]) -> dict[str, Any]:
    bench = _bench(row)
    return {
        "status": str(row.get("status") or ""),
        "delivery_status": str(bench.get("status") or ""),
        "success_rate": 1.0 if row.get("status") == "PASS" and bench.get("status") == "SUCCESS" else 0.0,
        "total_tokens": _number(bench, "total_tokens"),
        "phase_wall_total_sec": _number(bench, "phase_wall_total_sec"),
        "trust_mismatch": bool(bench.get("report_trust_mismatch") or bench.get("trust_mismatch")),
        "receipt_chain_pass": _receipt_chain_pass(row),
        "skill_mount_contract_status": str(bench.get("skill_mount_contract_status") or ""),
        "infra_invalid_reason": str(bench.get("infra_invalid_reason") or ""),
        "evidence_path": str(_gate(row).get("evidence_path") or ""),
        "receipt_path": str(_gate(row).get("receipt_path") or ""),
    }


def _decision(*, current: Mapping[str, Any], candidate: Mapping[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    for label, metrics in (("current", current), ("candidate", candidate)):
        if metrics["infra_invalid_reason"]:
            reasons.append(f"{label}_infra_invalid:{metrics['infra_invalid_reason']}")
            return "HOLD_MISSING_LIVE_EVIDENCE", reasons
        if metrics["trust_mismatch"]:
            reasons.append(f"{label}_trust_mismatch")
            return "HOLD_MISSING_LIVE_EVIDENCE", reasons
        if not metrics["receipt_chain_pass"]:
            reasons.append(f"{label}_receipt_chain_incomplete")
            return "HOLD_MISSING_LIVE_EVIDENCE", reasons
        if metrics["success_rate"] < 1.0:
            reasons.append(f"{label}_delivery_not_success")
            return "HOLD_MISSING_LIVE_EVIDENCE", reasons
    if candidate["total_tokens"] is None or current["total_tokens"] is None:
        reasons.append("missing_provider_token_truth")
        return "HOLD_MISSING_LIVE_EVIDENCE", reasons
    if candidate["phase_wall_total_sec"] is None or current["phase_wall_total_sec"] is None:
        reasons.append("missing_wall_truth")
        return "HOLD_MISSING_LIVE_EVIDENCE", reasons
    token_delta = candidate["total_tokens"] - current["total_tokens"]
    wall_delta = round(float(candidate["phase_wall_total_sec"]) - float(current["phase_wall_total_sec"]), 4)
    if token_delta > 0 or wall_delta > 0:
        reasons.append("candidate_efficiency_regressed")
        return "KEEP_CURRENT_PRIMARY", reasons
    return "REPLACE_PRIMARY_LIVE_APPROVED", reasons


def build_sf_final_live_compare_report(*, live_summary: Mapping[str, Any]) -> dict[str, Any]:
    results = [row for row in live_summary.get("results", []) or [] if isinstance(row, Mapping)]
    by_key: dict[tuple[str, str], dict[str, Mapping[str, Any]]] = {}
    for row in results:
        capability = str(row.get("capability") or "")
        task_ref = row.get("task_ref") if isinstance(row.get("task_ref"), Mapping) else {}
        task_id = str(task_ref.get("task_id") or "")
        arm_id = str(row.get("arm_id") or "")
        if capability and task_id and arm_id:
            by_key.setdefault((capability, task_id), {})[arm_id] = row

    comparisons: list[dict[str, Any]] = []
    blockers: list[str] = []
    for (capability, task_id), arms in sorted(by_key.items()):
        current_row = arms.get("current_primary_skill")
        candidate_row = arms.get("candidate_skill")
        if current_row is None or candidate_row is None:
            blockers.append(f"{capability}:{task_id}:missing_current_candidate_pair")
            continue
        current = _row_metrics(current_row)
        candidate = _row_metrics(candidate_row)
        token_delta = None
        if current["total_tokens"] is not None and candidate["total_tokens"] is not None:
            token_delta = candidate["total_tokens"] - current["total_tokens"]
        wall_delta = None
        if current["phase_wall_total_sec"] is not None and candidate["phase_wall_total_sec"] is not None:
            wall_delta = round(float(candidate["phase_wall_total_sec"]) - float(current["phase_wall_total_sec"]), 4)
        verdict, reasons = _decision(current=current, candidate=candidate)
        comparisons.append(
            {
                "capability": capability,
                "task_id": task_id,
                "current_row_id": current_row.get("row_id", ""),
                "candidate_row_id": candidate_row.get("row_id", ""),
                "current_skill_id": current_row.get("skill_id", ""),
                "candidate_skill_id": candidate_row.get("skill_id", ""),
                "current": current,
                "candidate": candidate,
                "delta": {
                    "token_delta": token_delta,
                    "wall_delta": wall_delta,
                    "success_rate_delta": round(float(candidate["success_rate"]) - float(current["success_rate"]), 4),
                },
                "verdict": verdict,
                "reason_codes": reasons,
            }
        )

    return {
        "schema": "nexus.sf_final_live_compare_report.v1",
        "status": "PASS" if comparisons and not blockers else "RETURN",
        "summary": {
            "comparison_count": len(comparisons),
            "replace_live_approved_count": sum(1 for item in comparisons if item["verdict"] == "REPLACE_PRIMARY_LIVE_APPROVED"),
            "keep_current_count": sum(1 for item in comparisons if item["verdict"] == "KEEP_CURRENT_PRIMARY"),
            "hold_count": sum(1 for item in comparisons if item["verdict"] == "HOLD_MISSING_LIVE_EVIDENCE"),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "blockers": blockers,
        "comparisons": comparisons,
        "claim_boundary": [
            "This is internal Flash+Nexus live skill-pair evidence only.",
            "Replacement is catalog-map eligible only when verdict is REPLACE_PRIMARY_LIVE_APPROVED.",
            "Runtime default and public benchmark remain separate gates.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SF final live current-vs-candidate comparison report.")
    parser.add_argument("--live-summary", default=str(DEFAULT_LIVE_SUMMARY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    report = build_sf_final_live_compare_report(live_summary=read_json(args.live_summary))
    write_json(args.output, report)
    print(json.dumps({"status": report["status"], **report["summary"], "output": str(args.output)}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
