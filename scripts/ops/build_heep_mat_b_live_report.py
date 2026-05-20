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


DEFAULT_LIVE_SUMMARY = Path(".nexus/reports/heep_flash_nexus_mat_b_live_2026-05-20/live_summary.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_HEEP_MAT_B_LIVE_REPORT_2026-05-20.json")


def _metric_number(row: Mapping[str, Any], key: str) -> float | int | None:
    value = row.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _bench(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("benchmark_row")
    return value if isinstance(value, Mapping) else {}


def _gate(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("ablation_gate_row")
    return value if isinstance(value, Mapping) else {}


def _success_rate(row: Mapping[str, Any]) -> float:
    bench = _bench(row)
    return 1.0 if row.get("status") == "PASS" and bench.get("status") == "SUCCESS" else 0.0


def _pollution_pct(row: Mapping[str, Any]) -> float:
    bench = _bench(row)
    polluted = any(
        bool(bench.get(key))
        for key in (
            "report_trust_mismatch",
            "runner_overhead_polluted",
            "model_attempt_runner_overhead_polluted",
        )
    )
    return 100.0 if polluted else 0.0


def _receipt_chain_pass(row: Mapping[str, Any]) -> bool:
    gate = _gate(row)
    return all(bool(gate.get(key)) for key in ("selected", "injected", "used", "evidence_present", "gate_passed", "outcome_contributed"))


def _evidence_seal_count(row: Mapping[str, Any]) -> int:
    bench = _bench(row)
    return int(bench.get("skill_mount_count") or 0) if _receipt_chain_pass(row) else 0


def _row_metrics(row: Mapping[str, Any]) -> dict[str, Any]:
    bench = _bench(row)
    return {
        "success_rate": _success_rate(row),
        "pollution_pct": _pollution_pct(row),
        "evidence_seal_count": _evidence_seal_count(row),
        "total_tokens": _metric_number(bench, "total_tokens"),
        "phase_wall_total_sec": _metric_number(bench, "phase_wall_total_sec"),
        "reopen_rate": _metric_number(bench, "reopen_rate"),
        "trust_mismatch": bool(bench.get("report_trust_mismatch")),
        "skill_mount_contract_status": bench.get("skill_mount_contract_status", ""),
        "receipt_chain_pass": _receipt_chain_pass(row),
    }


def _decision(*, baseline: Mapping[str, Any], challenger: Mapping[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if challenger["success_rate"] < baseline["success_rate"] or challenger["success_rate"] < 1.0:
        reasons.append("reliability_not_better_or_delivery_return")
        return "REJECT_MULTI_SKILL", reasons
    if challenger["pollution_pct"] > baseline["pollution_pct"]:
        reasons.append("quality_pollution_regressed")
        return "REJECT_MULTI_SKILL", reasons
    if challenger["evidence_seal_count"] < baseline["evidence_seal_count"] or not challenger["receipt_chain_pass"]:
        reasons.append("governance_evidence_chain_incomplete")
        return "REJECT_MULTI_SKILL", reasons
    token_delta = None
    if baseline["total_tokens"] is not None and challenger["total_tokens"] is not None:
        token_delta = challenger["total_tokens"] - baseline["total_tokens"]
    wall_delta = None
    if baseline["phase_wall_total_sec"] is not None and challenger["phase_wall_total_sec"] is not None:
        wall_delta = round(float(challenger["phase_wall_total_sec"]) - float(baseline["phase_wall_total_sec"]), 4)
    if token_delta is None or wall_delta is None:
        reasons.append("missing_efficiency_truth")
        return "HOLD_MISSING_MAT_B_EVIDENCE", reasons
    if token_delta > 0 or wall_delta > 0:
        reasons.append("efficiency_regressed")
        return "KEEP_SINGLE_PRIMARY", reasons
    if challenger["reopen_rate"] is None or baseline["reopen_rate"] is None:
        reasons.append("missing_reopen_rate")
        return "HOLD_MISSING_MAT_B_EVIDENCE", reasons
    if challenger["reopen_rate"] > baseline["reopen_rate"]:
        reasons.append("regression_reopen_rate_regressed")
        return "REJECT_MULTI_SKILL", reasons
    return "APPROVE_HEEP_MODE_CANDIDATE", reasons


def build_heep_mat_b_live_report(*, live_summary: Mapping[str, Any]) -> dict[str, Any]:
    results = [row for row in live_summary.get("results", []) or [] if isinstance(row, Mapping)]
    by_key: dict[tuple[str, str], dict[str, Mapping[str, Any]]] = {}
    for row in results:
        capability = str(row.get("capability") or "")
        task_ref = row.get("task_ref") if isinstance(row.get("task_ref"), Mapping) else {}
        task_id = str(task_ref.get("task_id") or "")
        arm_id = str(row.get("arm_id") or "")
        if capability and task_id and arm_id:
            by_key.setdefault((capability, task_id), {})[arm_id] = row
    comparisons = []
    blockers = []
    for (capability, task_id), arms in sorted(by_key.items()):
        baseline_row = arms.get("mode_a_current_primary")
        challenger_row = arms.get("heep_multi_skill")
        if baseline_row is None or challenger_row is None:
            blockers.append(f"{capability}:{task_id}:missing_mat_b_pair")
            continue
        baseline = _row_metrics(baseline_row)
        challenger = _row_metrics(challenger_row)
        token_delta = None
        if baseline["total_tokens"] is not None and challenger["total_tokens"] is not None:
            token_delta = challenger["total_tokens"] - baseline["total_tokens"]
        wall_delta = None
        if baseline["phase_wall_total_sec"] is not None and challenger["phase_wall_total_sec"] is not None:
            wall_delta = round(float(challenger["phase_wall_total_sec"]) - float(baseline["phase_wall_total_sec"]), 4)
        verdict, reasons = _decision(baseline=baseline, challenger=challenger)
        comparisons.append(
            {
                "capability": capability,
                "task_id": task_id,
                "baseline_row_id": baseline_row.get("row_id", ""),
                "challenger_row_id": challenger_row.get("row_id", ""),
                "baseline": baseline,
                "challenger": challenger,
                "delta": {
                    "token_delta": token_delta,
                    "wall_delta": wall_delta,
                    "success_rate_delta": round(float(challenger["success_rate"]) - float(baseline["success_rate"]), 4),
                    "pollution_pct_delta": round(float(challenger["pollution_pct"]) - float(baseline["pollution_pct"]), 4),
                    "evidence_seal_count_delta": challenger["evidence_seal_count"] - baseline["evidence_seal_count"],
                    "reopen_rate_delta": None
                    if challenger["reopen_rate"] is None or baseline["reopen_rate"] is None
                    else round(float(challenger["reopen_rate"]) - float(baseline["reopen_rate"]), 4),
                },
                "verdict": verdict,
                "reason_codes": reasons,
            }
        )
    return {
        "schema": "nexus.heep_mat_b_live_report.v1",
        "status": "PASS" if not blockers else "RETURN",
        "summary": {
            "comparison_count": len(comparisons),
            "approve_count": sum(1 for item in comparisons if item["verdict"] == "APPROVE_HEEP_MODE_CANDIDATE"),
            "keep_single_count": sum(1 for item in comparisons if item["verdict"] == "KEEP_SINGLE_PRIMARY"),
            "reject_count": sum(1 for item in comparisons if item["verdict"] == "REJECT_MULTI_SKILL"),
            "hold_count": sum(1 for item in comparisons if item["verdict"] == "HOLD_MISSING_MAT_B_EVIDENCE"),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "blockers": blockers,
        "comparisons": comparisons,
        "claim_boundary": [
            "This report is internal HEEP MAT-B live evidence only.",
            "It can update HEEP mode candidates and runtime apply review packets, not runtime defaults.",
            "It is not a public benchmark or publication-ready claim.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build HEEP MAT-B live comparison report.")
    parser.add_argument("--live-summary", default=str(DEFAULT_LIVE_SUMMARY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    report = build_heep_mat_b_live_report(live_summary=read_json(args.live_summary))
    write_json(args.output, report)
    print(json.dumps({"status": report["status"], **report["summary"], "output": str(args.output)}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
