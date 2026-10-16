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


DEFAULT_REPORT = Path("docs/reports/NEXUS_HEEP_MAT_B_LIVE_REPORT_2026-05-20.json")
DEFAULT_REPLAY_REPORT = Path("docs/reports/NEXUS_HEEP_MAT_B_HOLD_CLEAN_REPLAY_REPORT_2026-05-20.json")
DEFAULT_OUTPUT = DEFAULT_REPORT
TOKEN_BLOCKER = "BLOCKED_BY_PROVIDER_TOKEN_TRUTH"
RECEIPT_BLOCKER = "BLOCKED_BY_RECEIPT_DATA_CONTRACT"


def _comparisons_by_capability(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("capability") or ""): dict(row)
        for row in (report.get("comparisons", []) or [])
        if isinstance(row, Mapping) and row.get("capability")
    }


def _blocker_verdict(reason_codes: list[str]) -> str:
    joined = " ".join(reason_codes)
    if "model_call_without_tokens" in joined:
        return TOKEN_BLOCKER
    if "receipt_data_contract_violation" in joined:
        return RECEIPT_BLOCKER
    return "BLOCKED_BY_UNCLEAN_MAT_B_EVIDENCE"


def finalize_heep_mat_b_holds(*, report: Mapping[str, Any], clean_replay_report: Mapping[str, Any]) -> dict[str, Any]:
    replay_by_capability = _comparisons_by_capability(clean_replay_report)
    comparisons = []
    finalized_count = 0
    for raw in report.get("comparisons", []) or []:
        if not isinstance(raw, Mapping):
            continue
        comparison = dict(raw)
        capability = str(comparison.get("capability") or "")
        if comparison.get("verdict") != "HOLD_MISSING_MAT_B_EVIDENCE":
            comparisons.append(comparison)
            continue
        replay = replay_by_capability.get(capability)
        if replay is None or replay.get("verdict") != "HOLD_MISSING_MAT_B_EVIDENCE":
            comparisons.append(comparison)
            continue
        original_reasons = [str(item) for item in comparison.get("reason_codes", []) or []]
        replay_reasons = [str(item) for item in replay.get("reason_codes", []) or []]
        comparison["verdict"] = _blocker_verdict([*original_reasons, *replay_reasons])
        comparison["reason_codes"] = [
            *original_reasons,
            "clean_replay_still_unclean",
            *(f"clean_replay:{reason}" for reason in replay_reasons),
        ]
        comparison["clean_replay"] = {
            "baseline_row_id": replay.get("baseline_row_id", ""),
            "challenger_row_id": replay.get("challenger_row_id", ""),
            "verdict": replay.get("verdict", ""),
            "reason_codes": replay_reasons,
        }
        finalized_count += 1
        comparisons.append(comparison)

    summary = {
        "comparison_count": len(comparisons),
        "approve_count": sum(1 for item in comparisons if item["verdict"] == "APPROVE_HEEP_MODE_CANDIDATE"),
        "keep_single_count": sum(1 for item in comparisons if item["verdict"] == "KEEP_SINGLE_PRIMARY"),
        "reject_count": sum(1 for item in comparisons if item["verdict"] == "REJECT_MULTI_SKILL"),
        "hold_count": sum(1 for item in comparisons if item["verdict"] == "HOLD_MISSING_MAT_B_EVIDENCE"),
        "final_blocker_count": sum(1 for item in comparisons if str(item["verdict"]).startswith("BLOCKED_BY_")),
        "finalized_hold_count": finalized_count,
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }
    return {
        **dict(report),
        "schema": "nexus.heep_mat_b_live_report.v2",
        "status": "PASS",
        "summary": summary,
        "comparisons": comparisons,
        "claim_boundary": [
            "This report is internal HEEP MAT-B live evidence only.",
            "Final blocker verdicts mean clean replay also failed the evidence contract; they are not skill-quality approvals.",
            "It can update HEEP mode candidates and runtime apply review packets, not runtime defaults.",
            "It is not a public benchmark or publication-ready claim.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize HEEP MAT-B HOLD rows after clean replay evidence.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--clean-replay-report", default=str(DEFAULT_REPLAY_REPORT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    finalized = finalize_heep_mat_b_holds(
        report=read_json(args.report),
        clean_replay_report=read_json(args.clean_replay_report),
    )
    write_json(args.output, finalized)
    print(json.dumps({"status": finalized["status"], **finalized["summary"], "output": args.output}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
